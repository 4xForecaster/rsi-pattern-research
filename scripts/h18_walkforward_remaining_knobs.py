#!/usr/bin/env python3
"""H18 — Walk-forward the remaining H14 knobs.

H17 walk-forward'd the strict-M thresholds. The H14 spec has four more
knobs that were also calibrated on the full 104-day window — same
paper-fit risk:

  1. FLD cycles            — H14 used (40, 80, 160) "canonical 2x harmonic"
  2. Range lookback bars   — H14 chose 1x longest FLD cycle = 160 via
                              Phase 1.4 sensitivity sweep on the FULL window
  3. Trail activation      — H14 used 3.600x (inherited from H13 / SURF Fib spec)
  4. Time stop bars        — H14 set to 1x longest FLD cycle = 160
  5. Scheme                — H14 Phase 2.5 picked C over D/E on the FULL window

Methodology mirrors H17: split the 104-day 5m DXY window 50/50, sweep
each knob ONE AT A TIME on the train slice with the other knobs held
at H14 defaults, then apply each tested setting to the test slice.
Per knob, report:
  - train winner vs H14 default
  - test winner vs H14 default
  - decay ratio for each setting (= test_sortino / train_sortino)
  - per-knob verdict: HOLDS_UP / PARTIAL_DECAY / PAPER_FIT / INCONCLUSIVE

Eligibility filter: ≥10 train trades AND ≥5 test trades.

Reports H14 numbers alongside per-knob train/test pairs. If a knob's
H14 default loses to a test alternative by a meaningful margin
(test Sortino +0.5 or more), flag it for spec revision.
"""
from __future__ import annotations
import itertools
import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import data as data_mod
from rsi_pattern import indicators, fld
from rsi_pattern import intraday as itd
from rsi_pattern import risk_metrics as rm
from rsi_pattern.patterns_strict import StrictPatternConfig

PERIODS_PER_YEAR_5M = 252 * 288

# H14 defaults (strict-M thresholds = H17's keep-decision)
H14 = {
    "fld_cycles":      (40, 80, 160),
    "range_lookback":  160,
    "trail_factor":    3.600,
    "time_stop":       160,
    "scheme_name":     "C",
    "scheme_mults":    (1.0, 1.0, 5.0),     # bullish / neutral / bearish
    "strict_origin":   30.0,
    "strict_peak":     72.0,
    "strict_wiggle":   72.0,
    "spread":          0.0003,
    "base_risk":       0.01,
}

# Per-knob sweeps. Each knob's H14 default is included so we can re-validate.
SWEEPS = {
    "fld_cycles": [(20, 40, 80), (40, 80, 160), (60, 120, 240)],
    "range_lookback": [80, 160, 320],
    "trail_factor": [3.000, 3.600, 4.000],
    "time_stop": [80, 160, 320],
    "scheme": [
        ("A", (1.0, 1.0, 1.0)),
        ("B", (1.0, 1.0, 3.0)),
        ("C", (1.0, 1.0, 5.0)),
        ("D", (0.0, 1.0, 3.0)),
        ("E", (0.5, 1.0, 3.0)),
    ],
}

MIN_TRAIN_TRADES = 10
MIN_TEST_TRADES = 5


def load_5m() -> pd.DataFrame:
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy("5m")


def run_cell(
    df: pd.DataFrame,
    *,
    fld_cycles: tuple,
    range_lookback: int,
    trail_factor: float,
    time_stop: int,
    scheme_mults: tuple,
) -> dict:
    """Run one Scheme-X strategy cell over `df` with the named knob values.

    Strict-M thresholds always fixed at H14 defaults (per H17).
    """
    df_rsi = indicators.add_rsi(df, period=14)
    df_rsi["atr14"] = itd.atr14(df_rsi)
    bias = fld.fld_bias(df_rsi, cycles=fld_cycles)
    scfg = StrictPatternConfig(
        rise_origin_below=H14["strict_origin"],
        major_peak_min=H14["strict_peak"],
        wiggle_trough_floor=H14["strict_wiggle"],
    )
    fib_trades = itd.build_fib_trades(
        df_rsi,
        detector="strict",
        range_rule="pre_p1",
        lookback_bars=range_lookback,
        stop_rule="structural",
        time_stop_bars=time_stop,
        strict_cfg=scfg,
        atr_series=df_rsi.get("atr14"),
    )
    # Manually override the trail activation factor inside the trade simulator.
    # build_fib_trades uses the module-level default; for the sweep we re-
    # simulate each trade with the desired trail_factor.
    if trail_factor != itd.TRAIL_ACTIVATION_FACTOR:
        from rsi_pattern.position_sizing import simulate_fib_trade, FibTrade, compute_fib_targets
        from rsi_pattern.patterns_strict import detect_strict_m
        rsi_series = df_rsi["rsi14"].dropna()
        strict_ms = detect_strict_m(rsi_series, scfg)
        fib_trades = []
        for sm in strict_ms:
            if sm.completion_idx is None:
                continue
            p1_rsi_pos = int(sm.first_major_peak_idx)
            try:
                p1_ts = rsi_series.index[p1_rsi_pos]
                entry_ts = rsi_series.index[p1_rsi_pos + 1]
                p1_df = df_rsi.index.get_loc(p1_ts)
                entry_df = df_rsi.index.get_loc(entry_ts)
            except (IndexError, KeyError):
                continue
            entry_price = float(df_rsi["close"].iloc[entry_df])
            lb = min(p1_df, range_lookback)
            if lb <= 0:
                continue
            seg = df_rsi.iloc[p1_df - lb:p1_df]
            low_pos = int(seg["low"].values.argmin() + (p1_df - lb))
            price_low = float(df_rsi["low"].iloc[low_pos])
            price_high = float(df_rsi["high"].iloc[p1_df])
            range_size = price_high - price_low
            if range_size <= 0:
                continue
            init_stop = float(df_rsi["low"].iloc[low_pos])
            if init_stop >= entry_price:
                continue
            targets = compute_fib_targets(entry_price, range_size, "long")
            t = FibTrade(direction="long", entry_idx=entry_df,
                         entry_price=entry_price, range_size=range_size,
                         range_high_idx=p1_df, range_low_idx=low_pos,
                         initial_stop=init_stop, targets=targets)
            t = simulate_fib_trade(df_rsi, t, max_bars=time_stop,
                                    trail_activation_factor=trail_factor)
            fib_trades.append(t)

    # Scheme multipliers
    bull_m, neut_m, bear_m = scheme_mults
    mults = []
    for t in fib_trades:
        if t.exit_idx is None or t.r_multiple is None:
            mults.append(0.0)
            continue
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        if lbl == "bullish":
            mults.append(bull_m)
        elif lbl == "bearish":
            mults.append(bear_m)
        else:
            mults.append(neut_m)

    r_records = []
    for t, m in zip(fib_trades, mults):
        if t.exit_idx is None or t.r_multiple is None or m == 0:
            continue
        r_records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(df_rsi.index[t.entry_idx]),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(m),
        ))
    mtm = itd.fib_to_mtm(fib_trades, df_rsi, mults, spread=H14["spread"])
    equity = rm.build_equity_curve_mtm(
        mtm, df_rsi["close"], initial_capital=1.0, risk_per_trade=H14["base_risk"],
    )
    return {
        "trades": len(r_records),
        "mean_R_weighted": (float(np.mean([r.r_multiple * r.multiplier for r in r_records]))
                            if r_records else float("nan")),
        "total_R_per_year": rm.total_r_per_year(r_records),
        "sharpe": rm.sharpe(equity, periods_per_year=PERIODS_PER_YEAR_5M),
        "sortino": rm.sortino(equity, periods_per_year=PERIODS_PER_YEAR_5M),
        "max_dd": rm.max_drawdown(equity),
    }


def knob_setting(knob: str, value, base: dict) -> dict:
    """Return a kwargs dict for run_cell with `knob` set to `value`."""
    out = dict(base)
    if knob == "fld_cycles":
        out["fld_cycles"] = tuple(value)
    elif knob == "range_lookback":
        out["range_lookback"] = int(value)
    elif knob == "trail_factor":
        out["trail_factor"] = float(value)
    elif knob == "time_stop":
        out["time_stop"] = int(value)
    elif knob == "scheme":
        # value is (name, mults)
        out["scheme_mults"] = tuple(value[1])
    return out


def base_kwargs() -> dict:
    return {
        "fld_cycles":      H14["fld_cycles"],
        "range_lookback":  H14["range_lookback"],
        "trail_factor":    H14["trail_factor"],
        "time_stop":       H14["time_stop"],
        "scheme_mults":    H14["scheme_mults"],
    }


def verdict(train_sortino: float, test_sortino: float, test_trades: int) -> tuple[str, str]:
    if test_trades < MIN_TEST_TRADES or np.isnan(test_sortino):
        return "INCONCLUSIVE", f"test trades={test_trades} too few or Sortino undefined"
    if train_sortino <= 0:
        return "INCONCLUSIVE", f"train Sortino {train_sortino:.2f} ≤ 0"
    ratio = test_sortino / train_sortino
    if ratio >= 0.66:
        return "HOLDS_UP", f"ratio {ratio:.2f} ≥ 0.66"
    if ratio >= 0.33:
        return "PARTIAL_DECAY", f"ratio {ratio:.2f} ∈ [0.33, 0.66)"
    return "PAPER_FIT", f"ratio {ratio:.2f} < 0.33"


def value_label(knob: str, value) -> str:
    if knob == "fld_cycles":
        return f"{value}"
    if knob == "scheme":
        return f"{value[0]} {value[1]}"
    return f"{value}"


def main():
    df = load_5m()
    midpoint_ts = df.index[0] + (df.index[-1] - df.index[0]) / 2
    df_train = df[df.index < midpoint_ts].copy()
    df_test = df[df.index >= midpoint_ts].copy()

    print("=" * 84)
    print("H18 — Walk-forward of remaining H14 knobs (FLD cycles, lookback, trail, time-stop, scheme)")
    print("=" * 84)
    print(f"5m bars: {len(df)} total")
    print(f"TRAIN: {len(df_train)} bars, {df_train.index[0]} → {df_train.index[-1]}")
    print(f"TEST:  {len(df_test)} bars, {df_test.index[0]} → {df_test.index[-1]}")
    print()

    out_rows = []
    revisions = []   # knobs where the H14 default loses to a test alternative

    for knob, settings in SWEEPS.items():
        print(f"--- {knob} (H14 default: {value_label(knob, _h14_value(knob))}) ---")
        print(f"  {'value':<22} {'train_tr':>9} {'tr_meanR':>9} {'tr_Srt':>7} {'tr_DD':>7}  "
              f"|  {'test_tr':>8} {'te_meanR':>9} {'te_Srt':>7} {'te_DD':>7}  | verdict")
        rows = []
        for v in settings:
            kw_train = knob_setting(knob, v, base_kwargs())
            kw_test = knob_setting(knob, v, base_kwargs())
            m_train = run_cell(df_train, **kw_train)
            m_test = run_cell(df_test, **kw_test)
            vd, reason = verdict(m_train["sortino"], m_test["sortino"], m_test["trades"])
            row = {
                "knob": knob,
                "value": value_label(knob, v),
                "is_h14_default": _is_h14(knob, v),
                "train": m_train, "test": m_test,
                "verdict": vd, "verdict_reason": reason,
            }
            rows.append(row)
            marker = "  ← H14" if _is_h14(knob, v) else ""
            print(f"  {value_label(knob, v):<22} "
                  f"{m_train['trades']:>9d} {m_train['mean_R_weighted']:>+9.2f} "
                  f"{m_train['sortino']:>+7.2f} {m_train['max_dd']*100:>+6.2f}%  |  "
                  f"{m_test['trades']:>8d} {m_test['mean_R_weighted']:>+9.2f} "
                  f"{m_test['sortino']:>+7.2f} {m_test['max_dd']*100:>+6.2f}%  | {vd}{marker}")

        # Identify best test setting vs H14 default
        valid = [r for r in rows
                 if r["test"]["trades"] >= MIN_TEST_TRADES
                 and not np.isnan(r["test"]["sortino"])]
        if valid:
            best_test = max(valid, key=lambda r: r["test"]["sortino"])
            h14_row = next((r for r in rows if r["is_h14_default"]), None)
            if h14_row and best_test is not h14_row:
                margin = best_test["test"]["sortino"] - h14_row["test"]["sortino"]
                if margin >= 0.5:
                    revisions.append({
                        "knob": knob,
                        "h14_value": value_label(knob, _h14_value(knob)),
                        "h14_test_sortino": h14_row["test"]["sortino"],
                        "winner_value": best_test["value"],
                        "winner_test_sortino": best_test["test"]["sortino"],
                        "margin": margin,
                    })
                    print(f"  → REVISION candidate: {best_test['value']} beats H14 default on test "
                          f"by Sortino +{margin:.2f}")
        out_rows.extend(rows)
        print()

    print("=" * 84)
    print("SUMMARY")
    print("=" * 84)
    if not revisions:
        print("No knob's H14 default loses by ≥ +0.5 test Sortino. All knobs hold up.")
    else:
        print("Knobs with a test-better alternative (≥ +0.5 Sortino margin):")
        for r in revisions:
            print(f"  - {r['knob']}: H14={r['h14_value']} (test Sortino {r['h14_test_sortino']:+.2f}) "
                  f"vs winner={r['winner_value']} (test {r['winner_test_sortino']:+.2f}, "
                  f"margin +{r['margin']:.2f})")

    # JSON dump
    json_path = REPO / "results" / "_h18_run.json"
    json_path.write_text(json.dumps({
        "h14_defaults": {k: (list(v) if isinstance(v, tuple) else v) for k, v in H14.items()},
        "train_window": [str(df_train.index[0]), str(df_train.index[-1]), len(df_train)],
        "test_window": [str(df_test.index[0]), str(df_test.index[-1]), len(df_test)],
        "min_train_trades": MIN_TRAIN_TRADES,
        "min_test_trades": MIN_TEST_TRADES,
        "rows": [
            {**r, "train": {k: (None if isinstance(v, float) and np.isnan(v) else v)
                            for k, v in r["train"].items()},
             "test": {k: (None if isinstance(v, float) and np.isnan(v) else v)
                      for k, v in r["test"].items()}}
            for r in out_rows
        ],
        "revisions": revisions,
    }, indent=2, default=str))
    print(f"\nWrote {json_path}")
    return 0


def _h14_value(knob: str):
    if knob == "fld_cycles":      return H14["fld_cycles"]
    if knob == "range_lookback":  return H14["range_lookback"]
    if knob == "trail_factor":    return H14["trail_factor"]
    if knob == "time_stop":       return H14["time_stop"]
    if knob == "scheme":          return (H14["scheme_name"], H14["scheme_mults"])


def _is_h14(knob: str, value) -> bool:
    if knob == "fld_cycles":
        return tuple(value) == H14["fld_cycles"]
    if knob == "range_lookback":
        return int(value) == H14["range_lookback"]
    if knob == "trail_factor":
        return abs(float(value) - H14["trail_factor"]) < 1e-9
    if knob == "time_stop":
        return int(value) == H14["time_stop"]
    if knob == "scheme":
        return value[0] == H14["scheme_name"]
    return False


if __name__ == "__main__":
    sys.exit(main())
