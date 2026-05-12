#!/usr/bin/env python3
"""H22 — V-floor-breach short, full backtest + walk-forward.

H10 documented V-floor breach as the LARGEST signal in the entire RSI
pattern system (Cohen's d ≈ -1.53 on daily DXY, large effects across
all timeframes). The function ``fib_short_at_v_floor`` already exists
in position_sizing.py but was never wrapped in the Scheme G framework
or risk-metric stack.

H21 found the SYMMETRIC short (V-T1, reversal entry) was a null —
0 bullish-FLD entries because RSI deeply oversold mechanically
forces price below all FLDs. H22 tests the asymmetric CONTINUATION
short: enter AFTER RSI breaches the V's floor (V failed to hold,
downside continues).

This is structurally different from H21's V-T1:
  H21 (V-T1):       enter at T1+1, after first trough but before V completes
                    → reversal trade, hoping price falls between T1 and T2
  H22 (V-floor):    enter after V completes AND breaches its own floor
                    → continuation trade, hoping the broken floor extends

Plan:
  Phase 1: full-window backtest on DAILY DXY (36 yrs), 5-scheme sweep
  Phase 2: walk-forward 70/30 (15 yrs train + 7 yrs test as in H15)
  Phase 3: if Phase 1 + 2 hold → port to 5m, side-by-side with M-P1 long
"""
from __future__ import annotations
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import data as data_mod
from rsi_pattern import indicators, fld
from rsi_pattern import position_sizing as ps
from rsi_pattern.patterns import PatternConfig
from rsi_pattern import risk_metrics as rm


# Same 5-scheme grid as H11/H12, but reading the columns as
# (bullish_FLD, neutral_FLD, bearish_FLD) — for SHORTS the
# "high-conviction" bucket is bullish FLD (price overextended above
# all slow FLDs = oversold opportunity for shorts when V-floor breaks).
SCHEMES_SHORT = {
    "A. Pure parallel (1/1/1)":      (1.0, 1.0, 1.0),
    "B. Modest (3/1/1)":             (3.0, 1.0, 1.0),
    "C. Aggressive (5/1/1)":         (5.0, 1.0, 1.0),
    "D. Skip bearish + 3x bullish":  (3.0, 1.0, 0.0),
    "E. Conservative (3/1/0.5)":     (3.0, 1.0, 0.5),
}

# Effect-size prior from H10
H10_EFFECT_SIZE = -1.53  # Cohen's d, daily V-floor breach 20d fwd

# H12 daily defaults
DAILY_SPREAD = 0.0002    # 2 bps
DAILY_BASE_RISK = 0.01
DAILY_FLD_CYCLES = (10, 20, 40)


def load_daily() -> pd.DataFrame:
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy("daily")


def run_scheme_daily(df: pd.DataFrame, scheme_mults: tuple) -> dict:
    df_rsi = indicators.add_rsi(df, period=14)
    bias = fld.fld_bias(df_rsi, cycles=DAILY_FLD_CYCLES)

    # Loose-V detector defaults (same as H10 reference run)
    fib_trades = ps.fib_short_at_v_floor(df_rsi, rsi_col="rsi14")

    bull_m, neut_m, bear_m = scheme_mults
    records, bias_counts = [], {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    for t in fib_trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        if lbl == "bullish":   mult = bull_m
        elif lbl == "bearish": mult = bear_m
        else:                  mult = neut_m
        if mult == 0:
            continue
        records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(entry_ts),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    equity = rm.build_equity_curve(records, initial_capital=1.0,
                                    risk_per_trade=DAILY_BASE_RISK)
    return {
        "trades": len(records),
        "universe": sum(1 for t in fib_trades if t.r_multiple is not None),
        "bias_counts": bias_counts,
        "mean_R_weighted": (float(np.mean([r.r_multiple * r.multiplier for r in records]))
                            if records else float("nan")),
        "total_R_per_year": rm.total_r_per_year(records),
        "sharpe": rm.sharpe(equity),
        "sortino": rm.sortino(equity),
        "calmar": rm.calmar(equity),
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
        "equity": equity,
    }


def fmt(m: dict) -> str:
    return (f"trades={m['trades']:>4d}  meanR={m['mean_R_weighted']:>+5.2f}  "
            f"R/yr={m['total_R_per_year']:>+6.2f}  "
            f"Sharpe={m['sharpe']:>+5.2f}  Sortino={m['sortino']:>+5.2f}  "
            f"MaxDD={m['max_dd']*100:>+6.2f}%")


def main():
    df = load_daily()
    n = len(df)
    span_yrs = (df.index[-1] - df.index[0]).days / 365.25

    print("=" * 84)
    print("H22 — V-floor-breach short on DAILY DXY")
    print("=" * 84)
    print(f"Daily bars: {n}, {df.index[0].date()} → {df.index[-1].date()} "
          f"({span_yrs:.1f} yrs)")
    print(f"H10 prior: Cohen's d ≈ {H10_EFFECT_SIZE} (large short signal)")
    print(f"Detector: loose-V (peaks≤35, inner≤50, completes >50)")
    print(f"Entry: breach+1 after V completion (continuation short)")
    print(f"FLD cycles: {DAILY_FLD_CYCLES}  spread: {DAILY_SPREAD*1e4:.1f} bps")
    print()

    # ── Phase 1: full-window 5-scheme sweep ──────────────────────────────
    print("--- Phase 1: 5-scheme sweep on FULL window ---")
    full_results = {}
    for name, mults in SCHEMES_SHORT.items():
        m = run_scheme_daily(df, mults)
        full_results[name] = m
        print(f"  {name:<32} {fmt(m)}")
        print(f"    bias: {m['bias_counts']}")

    # Phase 1 verdict
    base = full_results["A. Pure parallel (1/1/1)"]
    has_signal = (base["trades"] >= 30
                  and not np.isnan(base["sortino"])
                  and base["sortino"] > 0.5)
    if not has_signal:
        print()
        print("=" * 84)
        print(f"PHASE 1 VERDICT: NULL — V-floor breach short does not produce "
              f"a usable edge on daily DXY.")
        print(f"  Scheme A: trades={base['trades']}, "
              f"Sortino={base['sortino']:+.2f}, MeanR={base['mean_R_weighted']:+.2f}")
        print(f"  H10 reported Cohen's d = {H10_EFFECT_SIZE} which IS large in "
              f"absolute terms, but the SURF Fib trade structure may not capture it.")
        print("=" * 84)
        # No walk-forward — null at phase 1
        verdict = "NULL"
        winner_name = None
        wf_result = None
    else:
        # Pick winner by Sortino
        valid = sorted(
            [(n, m) for n, m in full_results.items()
             if m["trades"] >= 30 and not np.isnan(m["sortino"])],
            key=lambda x: -x[1]["sortino"],
        )
        winner_name, winner = valid[0]
        print(f"\nPhase 1 winner: {winner_name}  →  {fmt(winner)}")

        # ── Phase 2: walk-forward 70/30 ───────────────────────────────────
        print()
        print("--- Phase 2: walk-forward 70/30 on winning scheme ---")
        midpoint = df.index[int(n * 0.70)]
        df_train = df[df.index < midpoint].copy()
        df_test  = df[df.index >= midpoint].copy()
        print(f"TRAIN: {len(df_train)} bars, "
              f"{df_train.index[0].date()} → {df_train.index[-1].date()}")
        print(f"TEST:  {len(df_test)} bars, "
              f"{df_test.index[0].date()} → {df_test.index[-1].date()}")
        print()
        winner_mults = SCHEMES_SHORT[winner_name]
        m_train = run_scheme_daily(df_train, winner_mults)
        m_test  = run_scheme_daily(df_test, winner_mults)
        print(f"  {winner_name} train: {fmt(m_train)}")
        print(f"  {winner_name} test:  {fmt(m_test)}")

        # Verdict
        ts, tr = m_test["sortino"], m_train["sortino"]
        if np.isnan(ts) or m_test["trades"] < 10:
            verdict = "INCONCLUSIVE"
            reason = f"test trades={m_test['trades']} or Sortino undefined"
        elif tr <= 0:
            verdict = "INCONCLUSIVE"
            reason = f"train Sortino {tr:+.2f} <= 0"
        else:
            ratio = ts / tr
            if ratio >= 0.66:
                verdict = "HOLDS_UP"
                reason = f"test/train ratio {ratio:.2f} >= 0.66"
            elif ratio >= 0.33:
                verdict = "PARTIAL_DECAY"
                reason = f"test/train ratio {ratio:.2f} in [0.33, 0.66)"
            else:
                verdict = "PAPER_FIT"
                reason = f"test/train ratio {ratio:.2f} < 0.33"

        wf_result = {
            "winner_name": winner_name,
            "train": {k: v for k, v in m_train.items() if k != "equity"},
            "test": {k: v for k, v in m_test.items() if k != "equity"},
            "verdict": verdict,
            "verdict_reason": reason,
        }
        print(f"\nPhase 2 verdict: {verdict}  ({reason})")

        # Production gate (matches H17/H20 thresholds)
        ts = m_test["sortino"]
        tt = m_test["trades"]
        dd = m_test["max_dd"]
        if not np.isnan(ts) and ts >= 2.5 and tt >= 30 and dd > -0.15:
            prod_dec = "GO_CANDIDATE — proceed to 5m + cross-symbol"
        elif not np.isnan(ts) and ts >= 1.0:
            prod_dec = "MARGINAL — positive but below ship gates; document"
        else:
            prod_dec = "NOT_VIABLE — fails Sortino/trade/DD gates"
        print(f"\nPHASE 2 PRODUCTION DECISION: {prod_dec}")

    # ── Equity figure ─────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 6.5))
    colors = {"A. Pure parallel (1/1/1)":      "#888888",
              "B. Modest (3/1/1)":             "#4daf4a",
              "C. Aggressive (5/1/1)":         "#e41a1c",
              "D. Skip bearish + 3x bullish":  "#377eb8",
              "E. Conservative (3/1/0.5)":     "#984ea3"}
    for name, m in full_results.items():
        eq = m["equity"]
        ax.plot(eq.index, eq.values, label=name, color=colors.get(name, "#000"),
                linewidth=1.4)
    ax.axhline(1.0, color="black", linewidth=0.5, alpha=0.4)
    ax.set_title(
        "H22 — V-floor-breach short equity curves (daily DXY, full window)\n"
        f"H10 prior: Cohen's d ≈ {H10_EFFECT_SIZE}  ·  "
        f"detector: loose-V  ·  entry: breach+1  ·  spread {DAILY_SPREAD*1e4:.1f}bps",
        fontsize=10, pad=10,
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity (start = 1.0)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95)
    plt.tight_layout()
    fig_path = REPO / "figures" / "11_h22_v_floor_short.png"
    plt.savefig(fig_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {fig_path}")

    # ── JSON dump ─────────────────────────────────────────────────────────
    def _scrub(d):
        return {k: (None if isinstance(v, float) and np.isnan(v) else v)
                for k, v in d.items() if k != "equity"}
    out_path = REPO / "results" / "_h22_run.json"
    out_path.write_text(json.dumps({
        "timeframe": "daily",
        "data_window": [str(df.index[0]), str(df.index[-1]), n],
        "h10_prior_cohens_d": H10_EFFECT_SIZE,
        "detector": "loose_V",
        "entry_rule": "breach+1 after V completes",
        "fld_cycles": list(DAILY_FLD_CYCLES),
        "spread": DAILY_SPREAD,
        "base_risk": DAILY_BASE_RISK,
        "phase_1_full_window": {n: _scrub(m) for n, m in full_results.items()},
        "phase_1_verdict": verdict if not has_signal else "SIGNAL",
        "phase_2_walkforward": wf_result,
    }, indent=2, default=str))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
