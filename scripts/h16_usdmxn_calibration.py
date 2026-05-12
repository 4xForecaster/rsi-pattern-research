#!/usr/bin/env python3
"""H16 Part 2 — USDMXN calibration sweep.

H15 left USDMXN at Sortino +4.41 / 26 trades on full sample (SWEEP — Sortino
qualified, trade count 4 short of the 30-floor). This script runs the three
calibration variants proposed in H15 to see if any flips USDMXN to GO:

  variant A : loose-M dip threshold 50 -> 45 (shallower retraces qualify)
  variant B : FLD cycles (10,20,40) -> (15,30,60) (peso ~120D risk cycle)
  variant C : both A + B

IS/OOS protocol: calibrate on the first 70% of USDMXN history, evaluate
on the last 30%. OOS metrics are the load-bearing numbers.

GO threshold (this script applies both interpretations):
  STRICT    : OOS Sortino >= 3.0 AND OOS trades >= 30 AND OOS MaxDD > -10%
  PRAGMATIC : OOS Sortino >= 3.0 AND full-sample trades >= 30 AND OOS MaxDD > -10%
"""
from __future__ import annotations
import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import indicators, fld, position_sizing
from rsi_pattern.patterns import PatternConfig
from rsi_pattern import risk_metrics as rm

CACHE_PATH = REPO / "data" / "yfinance_cache" / "MXN_X_daily.csv"

SCHEME_D = (0.0, 1.0, 3.0)
IS_FRACTION = 0.70

# Three variants
VARIANTS = [
    {"name": "baseline (H15)", "dip": 50.0, "cycles": (10, 20, 40)},
    {"name": "variant_A (dip=45)", "dip": 45.0, "cycles": (10, 20, 40)},
    {"name": "variant_B (cycles=15/30/60)", "dip": 50.0, "cycles": (15, 30, 60)},
    {"name": "variant_C (both)", "dip": 45.0, "cycles": (15, 30, 60)},
]


def load_usdmxn() -> pd.DataFrame:
    if not CACHE_PATH.exists():
        raise FileNotFoundError(
            f"USDMXN cache missing at {CACHE_PATH}. Run scripts/h15_cross_symbol_validation.py first."
        )
    df = pd.read_csv(CACHE_PATH, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def run_one(df: pd.DataFrame, *, dip: float, cycles: tuple, label: str) -> dict:
    df_rsi = indicators.add_rsi(df, period=14)
    cfg = PatternConfig(m_inner_threshold=dip)
    trades = position_sizing.fib_long_at_p1(df_rsi, rsi_col="rsi14", cfg=cfg)
    bias = fld.fld_bias(df_rsi, cycles=cycles)

    bull_m, neut_m, bear_m = SCHEME_D
    records = []
    bias_counts = {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    universe = 0
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        universe += 1
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        if lbl == "bullish":
            mult = bull_m
        elif lbl == "bearish":
            mult = bear_m
        else:
            mult = neut_m
        if mult == 0:
            continue
        records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(entry_ts),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    equity = rm.build_equity_curve(records, initial_capital=1.0, risk_per_trade=0.01)
    return {
        "label": label,
        "trades": len(records),
        "universe": universe,
        "bias_counts": bias_counts,
        "mean_R_weighted": float(np.mean([r.r_multiple * r.multiplier for r in records])) if records else float("nan"),
        "total_R_per_year": rm.total_r_per_year(records),
        "sharpe": rm.sharpe(equity),
        "sortino": rm.sortino(equity),
        "calmar": rm.calmar(equity),
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
    }


def go_decision(oos: dict, full: dict) -> tuple[str, str]:
    sortino_ok = (not np.isnan(oos["sortino"])) and oos["sortino"] >= 3.0
    oos_trades_ok = oos["trades"] >= 30
    full_trades_ok = full["trades"] >= 30
    dd_ok = oos["max_dd"] > -0.10  # better than -10%

    if sortino_ok and oos_trades_ok and dd_ok:
        return "GO_STRICT", (
            f"OOS Sortino={oos['sortino']:+.2f}>=3.0, "
            f"OOS trades={oos['trades']}>=30, "
            f"OOS MaxDD={oos['max_dd']*100:+.2f}%> -10%"
        )
    if sortino_ok and full_trades_ok and dd_ok:
        return "GO_PRAGMATIC", (
            f"OOS Sortino={oos['sortino']:+.2f}>=3.0, "
            f"FULL trades={full['trades']}>=30 (OOS={oos['trades']}), "
            f"OOS MaxDD={oos['max_dd']*100:+.2f}%> -10%"
        )
    fails = []
    if not sortino_ok:
        fails.append(f"OOS Sortino={oos['sortino']:+.2f}<3.0")
    if not (oos_trades_ok or full_trades_ok):
        fails.append(f"trades insufficient (OOS={oos['trades']}, FULL={full['trades']})")
    if not dd_ok:
        fails.append(f"OOS MaxDD={oos['max_dd']*100:+.2f}%<= -10%")
    return "SWEEP", "; ".join(fails)


def main():
    df = load_usdmxn()
    n = len(df)
    is_end = int(n * IS_FRACTION)
    df_is = df.iloc[:is_end]
    df_oos = df.iloc[is_end:]

    print("=" * 72)
    print("H16 Part 2 — USDMXN calibration sweep")
    print("=" * 72)
    print(f"USDMXN daily: {n} bars total, {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"IS  (first 70%): {len(df_is):>5d} bars, {df_is.index[0].date()} -> {df_is.index[-1].date()}")
    print(f"OOS (last 30%):  {len(df_oos):>5d} bars, {df_oos.index[0].date()} -> {df_oos.index[-1].date()}")
    print()

    results = []
    for v in VARIANTS:
        is_metrics = run_one(df_is,  dip=v["dip"], cycles=v["cycles"], label=v["name"] + " IS")
        oos_metrics = run_one(df_oos, dip=v["dip"], cycles=v["cycles"], label=v["name"] + " OOS")
        full_metrics = run_one(df,    dip=v["dip"], cycles=v["cycles"], label=v["name"] + " FULL")
        decision, reason = go_decision(oos_metrics, full_metrics)
        results.append({
            "variant": v,
            "is": is_metrics,
            "oos": oos_metrics,
            "full": full_metrics,
            "decision": decision,
            "decision_reason": reason,
        })

    # Print
    hdr = f"{'Variant':<32} {'Slice':<5} {'Tr':>3} {'MeanR':>7} {'R/yr':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>8}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        for slice_name, m in [("IS", r["is"]), ("OOS", r["oos"]), ("FULL", r["full"])]:
            print(f"{r['variant']['name']:<32} {slice_name:<5} {m['trades']:>3} "
                  f"{m['mean_R_weighted']:>+7.2f} {m['total_R_per_year']:>+7.2f} "
                  f"{m['sharpe']:>+7.2f} {m['sortino']:>+8.2f} {m['max_dd']*100:>+7.2f}%")
        print()

    print("=" * 72)
    print("DECISIONS")
    print("=" * 72)
    for r in results:
        print(f"  {r['variant']['name']:<32} -> {r['decision']:<14} ({r['decision_reason']})")

    out = {
        "is_window": [str(df_is.index[0]), str(df_is.index[-1]), len(df_is)],
        "oos_window": [str(df_oos.index[0]), str(df_oos.index[-1]), len(df_oos)],
        "results": [
            {
                "variant": r["variant"],
                "is": {k: v for k, v in r["is"].items() if not isinstance(v, dict) or k == "bias_counts"},
                "oos": {k: v for k, v in r["oos"].items() if not isinstance(v, dict) or k == "bias_counts"},
                "full": {k: v for k, v in r["full"].items() if not isinstance(v, dict) or k == "bias_counts"},
                "decision": r["decision"],
                "decision_reason": r["decision_reason"],
            }
            for r in results
        ],
    }
    json_path = REPO / "results" / "_h16_usdmxn_run.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {json_path}")

    return results


if __name__ == "__main__":
    main()
