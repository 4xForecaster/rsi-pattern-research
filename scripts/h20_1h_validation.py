#!/usr/bin/env python3
"""H20 — 1h DXY validation.

H17/H18/H19 surfaced that the 5m strategy's published metrics are
fragile to small data shifts (104-day window, ~52-day train/test
slices, OOS Sortino swung from +4.17 → +2.23 between two pulls).
The honest production expectation became "+2 to +4 regime-dependent",
which is uncomfortably wide for capital allocation.

1h DXY has 3.25 years of history (1,186 days, 19,999 bars). A proper
70/30 walk-forward gives 2.27 years train and 1 year test —
dramatically more robust than 5m's 52/52 days.

This script applies the same H14 → H17 → H18 pipeline to 1h, asking:

  Phase 1 — Inventory + bias distribution.
  Phase 2 — Default-thresholds 5-scheme sweep (A/B/C/D/E) on FULL window,
            to establish a baseline analogous to H14 Phase 2.5.
  Phase 3 — 70/30 walk-forward:
            (a) Strict-M threshold sweep on TRAIN, score by Sortino on
                Scheme C, pick winner.
            (b) Evaluate winner + H14-default (30,72,72) on TEST.
            (c) Verdict per H17's bucket rule.
  Phase 4 — 5-scheme sweep on TRAIN slice + TEST slice using H14-default
            thresholds, to see if the scheme winner is stable.

Output:
  - prints per-phase tables to stdout
  - results/_h20_run.json with raw cell-level dumps
  - results/H20_1h_validation.md (writeup) — written separately

Decision rule for production-recommendation:
  - If 1h test Sortino > 2.5 AND test trades >= 30 AND DD better than -15%
    → 1h becomes a viable production candidate alongside 5m
  - If 1h test Sortino in (1.0, 2.5) → "mixed" — document and don't ship
  - Otherwise → 1h not viable as a primary production timeframe
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

TF = "1h"
PERIODS_PER_YEAR_1H = 252 * 24    # 6,048

# Same Scheme labels as H11/H12/H13/H14
SCHEMES = {
    "A. Pure parallel (1/1/1)":     (1.0, 1.0, 1.0),
    "B. Modest (1/1/3)":            (1.0, 1.0, 3.0),
    "C. Aggressive (1/1/5)":        (1.0, 1.0, 5.0),
    "D. Skip bullish + 3x (0/1/3)": (0.0, 1.0, 3.0),
    "E. Conservative (0.5/1/3)":    (0.5, 1.0, 3.0),
}

# Strict-M grid (matches H14 Phase 1.2 / H17)
ORIGIN_GRID = [25.0, 28.0, 30.0]
PEAK_GRID   = [72.0, 75.0, 78.0]
WIGGLE_GRID = [68.0, 70.0, 72.0]

# H14-default thresholds (H17 keep-decision)
H14_THR = (30.0, 72.0, 72.0)

# Train/test split
TRAIN_FRACTION = 0.70

# Eligibility floors
MIN_TRAIN_TRADES = 30   # 1h has way more data — raise floor vs H17's 10
MIN_TEST_TRADES  = 15


def load_1h() -> pd.DataFrame:
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy(TF)


def run_cell(
    df: pd.DataFrame,
    *,
    origin: float, peak: float, wiggle: float,
    scheme_mults: tuple,
) -> dict:
    """Apply Scheme-X on `df` with given strict-M thresholds.

    Uses H14 / H20 1h defaults for cycles, lookback, time-stop, trail,
    spread. Returns metric dict.
    """
    df_rsi = indicators.add_rsi(df, period=14)
    df_rsi["atr14"] = itd.atr14(df_rsi)
    bias = fld.fld_bias(df_rsi, cycles=itd.INTRADAY_FLD_CYCLES[TF])

    scfg = StrictPatternConfig(
        rise_origin_below=origin,
        major_peak_min=peak,
        wiggle_trough_floor=wiggle,
    )
    fib_trades = itd.build_fib_trades(
        df_rsi,
        detector="strict",
        range_rule="pre_p1",
        lookback_bars=itd.INTRADAY_FLD_CYCLES[TF][-1],
        stop_rule="structural",
        time_stop_bars=itd.INTRADAY_TIME_STOP_BARS[TF],
        strict_cfg=scfg,
        atr_series=df_rsi.get("atr14"),
    )

    bull_m, neut_m, bear_m = scheme_mults
    mults, bias_counts = [], {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    for t in fib_trades:
        if t.exit_idx is None or t.r_multiple is None:
            mults.append(0.0)
            continue
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        if lbl == "bullish":   mults.append(bull_m)
        elif lbl == "bearish": mults.append(bear_m)
        else:                  mults.append(neut_m)

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
    mtm = itd.fib_to_mtm(fib_trades, df_rsi, mults, spread=itd.INTRADAY_SPREAD[TF])
    equity = rm.build_equity_curve_mtm(
        mtm, df_rsi["close"], initial_capital=1.0, risk_per_trade=0.01,
    )
    return {
        "trades": len(r_records),
        "universe": sum(1 for t in fib_trades if t.r_multiple is not None),
        "bias_counts": bias_counts,
        "mean_R_weighted": (float(np.mean([r.r_multiple * r.multiplier for r in r_records]))
                            if r_records else float("nan")),
        "total_R_per_year": rm.total_r_per_year(r_records),
        "sharpe": rm.sharpe(equity, periods_per_year=PERIODS_PER_YEAR_1H),
        "sortino": rm.sortino(equity, periods_per_year=PERIODS_PER_YEAR_1H),
        "calmar": rm.calmar(equity, window_years=1.0),
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
    }


def verdict(train_s: float, test_s: float, test_tr: int) -> tuple[str, str]:
    if test_tr < MIN_TEST_TRADES or np.isnan(test_s):
        return "INCONCLUSIVE", f"test trades={test_tr}<{MIN_TEST_TRADES} or Sortino undefined"
    if train_s <= 0:
        return "INCONCLUSIVE", f"train Sortino {train_s:.2f} <= 0"
    ratio = test_s / train_s
    if ratio >= 0.66:
        return "HOLDS_UP", f"ratio {ratio:.2f} >= 0.66"
    if ratio >= 0.33:
        return "PARTIAL_DECAY", f"ratio {ratio:.2f} in [0.33, 0.66)"
    return "PAPER_FIT", f"ratio {ratio:.2f} < 0.33"


def production_decision(test: dict) -> tuple[str, str]:
    s = test["sortino"]
    n = test["trades"]
    dd = test["max_dd"]
    if np.isnan(s):
        return "NO-GO", "Sortino undefined"
    if s >= 2.5 and n >= 30 and dd > -0.15:
        return "VIABLE_1H_CANDIDATE", (
            f"OOS Sortino {s:+.2f}>=2.5, trades {n}>=30, "
            f"MaxDD {dd*100:+.2f}%>-15%"
        )
    if 1.0 <= s < 2.5:
        return "MIXED", f"OOS Sortino {s:+.2f} in (1.0, 2.5) — flag, don't ship"
    return "NOT_VIABLE", f"OOS Sortino {s:+.2f} or trades {n} or DD {dd*100:.2f}% fails threshold"


def fmt(m: dict) -> str:
    return (f"trades={m['trades']:>4d} meanR={m['mean_R_weighted']:>+5.2f} "
            f"R/yr={m['total_R_per_year']:>+6.2f} "
            f"Sharpe={m['sharpe']:>+5.2f} Sortino={m['sortino']:>+5.2f} "
            f"MaxDD={m['max_dd']*100:>+6.2f}%")


def main():
    df = load_1h()
    n = len(df)
    span_days = (df.index[-1] - df.index[0]).days

    print("=" * 84)
    print(f"H20 — 1h DXY validation (Scheme-D pipeline ported from 5m H14)")
    print("=" * 84)
    print(f"1h bars: {n}, span {span_days} days ({span_days/365.25:.2f} yrs)")
    print(f"  {df.index[0]} -> {df.index[-1]}")
    print(f"FLD cycles: {itd.INTRADAY_FLD_CYCLES[TF]}  "
          f"lookback={itd.INTRADAY_FLD_CYCLES[TF][-1]}  "
          f"time_stop={itd.INTRADAY_TIME_STOP_BARS[TF]}  "
          f"spread={itd.INTRADAY_SPREAD[TF]*1e4:.1f}bps")

    # ── Phase 2 — 5-scheme sweep on FULL window, H14 thresholds ───────────
    print()
    print("--- Phase 2: 5-scheme sweep (full window, H14 thresholds 30/72/72) ---")
    full_scheme = {}
    for name, mults in SCHEMES.items():
        m = run_cell(df, origin=H14_THR[0], peak=H14_THR[1], wiggle=H14_THR[2],
                     scheme_mults=mults)
        full_scheme[name] = m
        print(f"  {name:<30} {fmt(m)}")

    # Pick scheme winner on full window (highest Sortino, eligible)
    valid_schemes = [(n, m) for n, m in full_scheme.items()
                     if m["trades"] >= MIN_TRAIN_TRADES and not np.isnan(m["sortino"])]
    valid_schemes.sort(key=lambda x: -x[1]["sortino"])
    if valid_schemes:
        full_scheme_winner_name, _ = valid_schemes[0]
        print(f"  Phase 2 winner: {full_scheme_winner_name}")
    else:
        full_scheme_winner_name = "C. Aggressive (1/1/5)"
        print(f"  Phase 2: no eligible scheme — defaulting to {full_scheme_winner_name}")
    full_scheme_winner_mults = SCHEMES[full_scheme_winner_name]

    # ── Phase 3 — Walk-forward ────────────────────────────────────────────
    print()
    midpoint = df.index[int(n * TRAIN_FRACTION)]
    df_train = df[df.index < midpoint].copy()
    df_test  = df[df.index >= midpoint].copy()
    print(f"--- Phase 3: walk-forward ({TRAIN_FRACTION*100:.0f}/{(1-TRAIN_FRACTION)*100:.0f}) ---")
    print(f"  TRAIN: {len(df_train)} bars, {df_train.index[0]} → {df_train.index[-1]}")
    print(f"  TEST:  {len(df_test)} bars, {df_test.index[0]} → {df_test.index[-1]}")

    print(f"\n  Train grid (using {full_scheme_winner_name}, "
          f"min_train_trades={MIN_TRAIN_TRADES}):")
    train_cells = []
    for o, p, w in itertools.product(ORIGIN_GRID, PEAK_GRID, WIGGLE_GRID):
        m = run_cell(df_train, origin=o, peak=p, wiggle=w,
                      scheme_mults=full_scheme_winner_mults)
        m.update({"origin": o, "peak": p, "wiggle": w})
        train_cells.append(m)
    train_cells.sort(key=lambda c: -c["sortino"] if not np.isnan(c["sortino"]) else 1e9)

    eligible = [c for c in train_cells
                if c["trades"] >= MIN_TRAIN_TRADES and not np.isnan(c["sortino"])]
    print(f"    {'origin':>7} {'peak':>5} {'wig':>4} {'trades':>7} {'meanR':>7} "
          f"{'Sharpe':>7} {'Sortino':>8} {'MaxDD':>7}")
    for c in train_cells:
        flag = "  [skip<min]" if c["trades"] < MIN_TRAIN_TRADES else ""
        winner_flag = "  ← winner" if eligible and c is eligible[0] else ""
        h14_flag = "  ← H14"  if (c["origin"], c["peak"], c["wiggle"]) == H14_THR else ""
        print(f"    {c['origin']:>7} {c['peak']:>5} {c['wiggle']:>4} "
              f"{c['trades']:>7d} {c['mean_R_weighted']:>+7.2f} "
              f"{c['sharpe']:>+7.2f} {c['sortino']:>+8.2f} "
              f"{c['max_dd']*100:>+6.2f}%{flag}{winner_flag}{h14_flag}")

    if not eligible:
        print("\n[FATAL] no eligible training cell — abort phase 3")
        return 2
    winner_thr = (eligible[0]["origin"], eligible[0]["peak"], eligible[0]["wiggle"])
    test_winner = run_cell(df_test,
                            origin=winner_thr[0], peak=winner_thr[1], wiggle=winner_thr[2],
                            scheme_mults=full_scheme_winner_mults)
    test_h14 = run_cell(df_test,
                        origin=H14_THR[0], peak=H14_THR[1], wiggle=H14_THR[2],
                        scheme_mults=full_scheme_winner_mults)
    train_h14 = run_cell(df_train,
                         origin=H14_THR[0], peak=H14_THR[1], wiggle=H14_THR[2],
                         scheme_mults=full_scheme_winner_mults)

    print(f"\n  Test eval ({full_scheme_winner_name}):")
    print(f"    Train, winner ({winner_thr}):              {fmt(eligible[0])}")
    print(f"    Test,  winner (same thresholds applied):    {fmt(test_winner)}")
    print(f"    Train, H14 baseline (30,72,72):             {fmt(train_h14)}")
    print(f"    Test,  H14 baseline (30,72,72):             {fmt(test_h14)}")

    vd_winner, reason_winner = verdict(eligible[0]["sortino"], test_winner["sortino"],
                                        test_winner["trades"])
    vd_h14,    reason_h14    = verdict(train_h14["sortino"], test_h14["sortino"],
                                        test_h14["trades"])
    print(f"\n  Walk-forward verdict (train winner): {vd_winner} ({reason_winner})")
    print(f"  Walk-forward verdict (H14 baseline): {vd_h14} ({reason_h14})")

    # ── Phase 4 — 5-scheme sweep on train + test slices ───────────────────
    print()
    print("--- Phase 4: 5-scheme sweep, H14 thresholds, on each slice ---")
    print(f"  {'Scheme':<30} {'slice':<6} {fmt({'trades':0,'mean_R_weighted':float('nan'),'total_R_per_year':float('nan'),'sharpe':float('nan'),'sortino':float('nan'),'max_dd':0.0})[7:]}")
    phase4 = {}
    for name, mults in SCHEMES.items():
        m_train = run_cell(df_train, origin=H14_THR[0], peak=H14_THR[1], wiggle=H14_THR[2],
                            scheme_mults=mults)
        m_test  = run_cell(df_test,  origin=H14_THR[0], peak=H14_THR[1], wiggle=H14_THR[2],
                            scheme_mults=mults)
        phase4[name] = {"train": m_train, "test": m_test}
        print(f"  {name:<30} {'TRAIN':<6} {fmt(m_train)}")
        print(f"  {name:<30} {'TEST':<6} {fmt(m_test)}")

    # Production decision (use H14-baseline scheme C on test slice as anchor)
    prod_dec, prod_reason = production_decision(test_h14)
    print()
    print("=" * 84)
    print(f"PRODUCTION DECISION (1h, H14 baseline thresholds, "
          f"{full_scheme_winner_name}):  {prod_dec}")
    print(f"  reason: {prod_reason}")
    print("=" * 84)

    # JSON dump
    out_path = REPO / "results" / "_h20_run.json"
    def _scrub(d):
        return {k: (None if isinstance(v, float) and np.isnan(v) else v)
                for k, v in d.items()}
    out_path.write_text(json.dumps({
        "timeframe": TF,
        "data_window": [str(df.index[0]), str(df.index[-1]), n],
        "fld_cycles": list(itd.INTRADAY_FLD_CYCLES[TF]),
        "time_stop_bars": itd.INTRADAY_TIME_STOP_BARS[TF],
        "spread": itd.INTRADAY_SPREAD[TF],
        "train_window": [str(df_train.index[0]), str(df_train.index[-1]), len(df_train)],
        "test_window":  [str(df_test.index[0]),  str(df_test.index[-1]),  len(df_test)],
        "min_train_trades": MIN_TRAIN_TRADES,
        "min_test_trades": MIN_TEST_TRADES,
        "phase_2_full_window_5_scheme": {name: _scrub(m) for name, m in full_scheme.items()},
        "phase_2_winner": full_scheme_winner_name,
        "phase_3_train_cells": [_scrub(c) for c in train_cells],
        "phase_3_winner_thresholds": list(winner_thr),
        "phase_3_train_winner_metrics": _scrub(eligible[0]),
        "phase_3_test_winner_metrics": _scrub(test_winner),
        "phase_3_train_h14": _scrub(train_h14),
        "phase_3_test_h14": _scrub(test_h14),
        "phase_3_verdict_winner": vd_winner,
        "phase_3_verdict_h14":    vd_h14,
        "phase_4_scheme_x_slice": {name: {"train": _scrub(d["train"]),
                                          "test": _scrub(d["test"])}
                                    for name, d in phase4.items()},
        "production_decision": prod_dec,
        "production_decision_reason": prod_reason,
    }, indent=2, default=str))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
