#!/usr/bin/env python3
"""H17 — Walk-forward validation of H14 strict-M thresholds.

H14's calibration of (origin=30, peak=72, wiggle=72) used the same 104-day
window for both threshold selection and Sortino evaluation. Borderline
paper-fit. This script addresses it directly:

  1. Split the H14 5m DXY window 50/50 (52 days train, 52 days test).
  2. On TRAIN only: sweep the same 3×3×3 strict-M threshold grid
     (origin ∈ {25,28,30}, peak ∈ {72,75,78}, wiggle ∈ {68,70,72}).
     Score each cell by Sortino under Scheme C.
  3. Pick the cell with the best training Sortino (requires >=10 trades
     to avoid sparse-cell outliers).
  4. Apply those thresholds to the TEST slice. Report the full H12
     metric stack on both train and test.
  5. Compare to H14's published full-window numbers.

Outputs:
  - results/H17_walkforward_validation.md  (writeup)
  - results/_h17_run.json                  (raw cell-level dump)
  - prints train/test/H14 comparison table to stdout

If test_sortino << train_sortino: paper-fit confirmed, add a warning
banner to results/H14_intraday_TRADING_SPEC.md.
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

# Match h14_intraday_backtest.py constants
PERIODS_PER_YEAR_5M = 252 * 288  # 72,576

# Same grid as H14 Phase 1.2
ORIGIN_GRID = [25.0, 28.0, 30.0]
PEAK_GRID   = [72.0, 75.0, 78.0]
WIGGLE_GRID = [68.0, 70.0, 72.0]

# Scheme C — winning scheme for 5m per H14 Phase 2.5
SCHEME_C = (1.0, 1.0, 5.0)  # bullish / neutral / bearish

# Minimum trades for a training cell to be eligible as a winner
MIN_TRAIN_TRADES = 10

# H14 baseline thresholds + reference numbers (from results/H14_intraday_execution.md)
H14_BASELINE = {
    "origin": 30.0, "peak": 72.0, "wiggle": 72.0,
    "trades": 69, "sortino": 6.19, "sharpe": 4.03,
    "max_dd": -0.1351, "mean_R_weighted": 1.77, "total_R_per_year": 442.38,
    "window_days": 104, "window": "2026-01-21 → 2026-05-04",
}


def load_5m() -> pd.DataFrame:
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy("5m")


def run_one_cell(
    df: pd.DataFrame,
    *,
    origin: float, peak: float, wiggle: float,
    spread: float = 0.0003,
) -> dict:
    """Run Scheme C on `df` with given strict-M thresholds. Returns metrics."""
    df_rsi = indicators.add_rsi(df, period=14)
    df_rsi["atr14"] = itd.atr14(df_rsi)
    bias = fld.fld_bias(df_rsi, cycles=itd.INTRADAY_FLD_CYCLES["5m"])
    scfg = StrictPatternConfig(
        rise_origin_below=origin,
        major_peak_min=peak,
        wiggle_trough_floor=wiggle,
    )
    fib_trades = itd.build_fib_trades(
        df_rsi,
        detector="strict",
        range_rule="pre_p1",
        lookback_bars=itd.INTRADAY_FLD_CYCLES["5m"][-1],   # 160
        stop_rule="structural",
        time_stop_bars=itd.INTRADAY_TIME_STOP_BARS["5m"],
        strict_cfg=scfg,
        atr_series=df_rsi.get("atr14"),
    )
    bull_m, neut_m, bear_m = SCHEME_C
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
    # R-records (mean R / R/yr)
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
    # Overlap-aware MTM equity
    mtm = itd.fib_to_mtm(fib_trades, df_rsi, mults, spread=spread)
    equity = rm.build_equity_curve_mtm(
        mtm, df_rsi["close"], initial_capital=1.0, risk_per_trade=0.01,
    )
    return {
        "trades": len(r_records),
        "mean_R_weighted": (float(np.mean([r.r_multiple * r.multiplier for r in r_records]))
                            if r_records else float("nan")),
        "total_R_per_year": rm.total_r_per_year(r_records),
        "sharpe": rm.sharpe(equity, periods_per_year=PERIODS_PER_YEAR_5M),
        "sortino": rm.sortino(equity, periods_per_year=PERIODS_PER_YEAR_5M),
        "calmar": rm.calmar(equity, window_years=0.10),
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
    }


def main():
    df = load_5m()
    n = len(df)
    midpoint_ts = df.index[0] + (df.index[-1] - df.index[0]) / 2
    df_train = df[df.index <  midpoint_ts].copy()
    df_test  = df[df.index >= midpoint_ts].copy()

    print("=" * 76)
    print("H17 Part 2 — Walk-forward validation of H14 strict-M thresholds")
    print("=" * 76)
    print(f"5m bars total: {n}")
    print(f"TRAIN: {len(df_train)} bars, {df_train.index[0]} → {df_train.index[-1]}")
    print(f"TEST:  {len(df_test)} bars, {df_test.index[0]} → {df_test.index[-1]}")
    print()

    # Sweep grid on TRAIN
    print("--- TRAIN grid (27 cells, Scheme C) ---")
    train_cells = []
    for o, p, w in itertools.product(ORIGIN_GRID, PEAK_GRID, WIGGLE_GRID):
        m = run_one_cell(df_train, origin=o, peak=p, wiggle=w)
        m.update({"origin": o, "peak": p, "wiggle": w})
        train_cells.append(m)

    # Sort by Sortino, eligible cells only
    eligible = [c for c in train_cells
                if c["trades"] >= MIN_TRAIN_TRADES and not np.isnan(c["sortino"])]
    eligible.sort(key=lambda c: -c["sortino"])
    print(f"{'origin':>6} {'peak':>5} {'wig':>4} {'trades':>6} "
          f"{'meanR':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>7}")
    for c in sorted(train_cells, key=lambda c: -c["sortino"] if not np.isnan(c["sortino"]) else 1e9):
        marker = "  ←" if c is (eligible[0] if eligible else None) else ""
        if c["trades"] < MIN_TRAIN_TRADES:
            marker += "  [skip<min]"
        print(f"{c['origin']:>6} {c['peak']:>5} {c['wiggle']:>4} {c['trades']:>6} "
              f"{c['mean_R_weighted']:>+7.2f} {c['sharpe']:>+7.2f} "
              f"{c['sortino']:>+8.2f} {c['max_dd']*100:>+6.2f}%{marker}")

    if not eligible:
        print("\n[FATAL] no training cell met the min-trades threshold")
        return 2

    winner = eligible[0]
    print(f"\nTraining winner: origin={winner['origin']} peak={winner['peak']} "
          f"wiggle={winner['wiggle']}  "
          f"train_sortino={winner['sortino']:+.2f}  "
          f"train_trades={winner['trades']}")

    # Also explicitly evaluate H14 baseline thresholds on train AND test so
    # the writeup can compare apples-to-apples.
    print("\n--- TEST evaluation ---")
    test_winner = run_one_cell(df_test,
                                origin=winner["origin"],
                                peak=winner["peak"],
                                wiggle=winner["wiggle"])
    test_winner.update({"origin": winner["origin"], "peak": winner["peak"],
                        "wiggle": winner["wiggle"], "cell": "train-winner"})

    train_h14 = run_one_cell(df_train, origin=30.0, peak=72.0, wiggle=72.0)
    train_h14.update({"origin": 30.0, "peak": 72.0, "wiggle": 72.0,
                      "cell": "H14-baseline(30,72,72)"})
    test_h14 = run_one_cell(df_test, origin=30.0, peak=72.0, wiggle=72.0)
    test_h14.update({"origin": 30.0, "peak": 72.0, "wiggle": 72.0,
                     "cell": "H14-baseline(30,72,72)"})

    def fmt(m: dict) -> str:
        return (f"trades={m['trades']:>3} meanR={m['mean_R_weighted']:>+5.2f} "
                f"Sharpe={m['sharpe']:>+5.2f} Sortino={m['sortino']:>+5.2f} "
                f"MaxDD={m['max_dd']*100:>+6.2f}%")

    print(f"  Train, winner (origin={winner['origin']}, peak={winner['peak']}, "
          f"wig={winner['wiggle']}): {fmt(winner)}")
    print(f"  Test,  winner (same thresholds applied to held-out slice): {fmt(test_winner)}")
    print(f"  Train, H14 baseline (30,72,72): {fmt(train_h14)}")
    print(f"  Test,  H14 baseline (30,72,72): {fmt(test_h14)}")

    # Verdict
    train_sortino = winner["sortino"]
    test_sortino = test_winner["sortino"]
    if np.isnan(test_sortino) or test_winner["trades"] < 5:
        verdict = "INCONCLUSIVE"
        reason = f"test trades={test_winner['trades']} too few for stable Sortino"
    else:
        ratio = test_sortino / train_sortino if train_sortino > 0 else 0.0
        if ratio >= 0.66:
            verdict = "HOLDS_UP"
            reason = f"test/train Sortino ratio {ratio:.2f} ≥ 0.66"
        elif ratio >= 0.33:
            verdict = "PARTIAL_DECAY"
            reason = f"test/train Sortino ratio {ratio:.2f} ∈ [0.33, 0.66)"
        else:
            verdict = "PAPER_FIT"
            reason = f"test/train Sortino ratio {ratio:.2f} < 0.33"
    print(f"\nVERDICT: {verdict} — {reason}")

    # Dump JSON
    out = {
        "train_window": [str(df_train.index[0]), str(df_train.index[-1]), len(df_train)],
        "test_window":  [str(df_test.index[0]),  str(df_test.index[-1]),  len(df_test)],
        "grid": {"origin": ORIGIN_GRID, "peak": PEAK_GRID, "wiggle": WIGGLE_GRID},
        "min_train_trades": MIN_TRAIN_TRADES,
        "scheme": "C",
        "train_cells": [{k: (None if isinstance(v, float) and np.isnan(v) else v)
                         for k, v in c.items()} for c in train_cells],
        "winner_thresholds": {k: winner[k] for k in ("origin", "peak", "wiggle")},
        "train_winner_metrics": {k: (None if isinstance(v, float) and np.isnan(v) else v)
                                 for k, v in winner.items()},
        "test_winner_metrics":  {k: (None if isinstance(v, float) and np.isnan(v) else v)
                                 for k, v in test_winner.items()},
        "train_h14_baseline":   {k: (None if isinstance(v, float) and np.isnan(v) else v)
                                 for k, v in train_h14.items()},
        "test_h14_baseline":    {k: (None if isinstance(v, float) and np.isnan(v) else v)
                                 for k, v in test_h14.items()},
        "h14_full_window_reference": H14_BASELINE,
        "verdict": verdict,
        "verdict_reason": reason,
    }
    json_path = REPO / "results" / "_h17_run.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
