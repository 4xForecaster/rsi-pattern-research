#!/usr/bin/env python3
"""H24 — OOS robustness pass on the thin GO pairs (GBPUSD, NZDUSD).

H23 labelled GBPUSD (9 OOS trades) and NZDUSD (4 OOS trades) GO by the
locked rule but flagged both as thin-OOS and explicitly NOT safe to flip
live without this pass. H24 stress-tests the OOS slice four ways and
applies a locked decision precedence. No new parameters — this is a
robustness test of the *existing* framework, not a re-tune.

Engine parity: the OOS trade list is reconstructed with the exact H23 /
H16 path (loose-M PatternConfig dip=50, fld_bias (10,20,40), Scheme D
0/1/3, rm.build_equity_curve -> rm.sortino, 70/30 split by bars). Caches
under data/yfinance_cache/ — no network, fully reproducible.

Tests
-----
1. Bootstrap resampling (N=10000, seed 42): resample the OOS TradeRecord
   list with replacement, rebuild the equity curve, recompute Sortino.
   Report p5/p50/p95. Degenerate resamples (Sortino undefined — e.g. no
   downside, <2 daily returns) are mapped to 0.0 for the *decision*
   percentile (conservative, per the no-spurious-ship doctrine) and the
   nan-rate is reported separately for transparency.
2. Rolling-window stability: OOS calendar span, window = 50% of span,
   4 windows at start-fractions linspace(0, 0.5, 4) (each 50% wide; the
   last ends exactly at span end). Sortino per window (nan if <2 trades).
   Count windows >= +3.0.
3. Trade-clustering: Gini of per-trade contributions (r*mult) via the
   classic sorted-rank formula, PLUS the single-30-day-window profit
   share as corroboration. Flag if Gini > 0.7.
4. Per-trade sensitivity: drop each OOS trade once, recompute Sortino on
   the N-1 remainder. Report min and the trade that causes it.

Decision precedence (locked, in order)
--------------------------------------
- SOLID GO   : ALL of {boot p5 >= +3.0, >=3/4 rolling >= +3.0,
                        Gini <= 0.7, per-trade min-Sortino >= +2.5}
- THIN GO    : 2 or 3 of the 4 hold
- DOWNGRADE  : 0 or 1 hold -> status: sweep_needed
`enabled` stays false either way.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import indicators, fld, position_sizing
from rsi_pattern.patterns import PatternConfig
from rsi_pattern import risk_metrics as rm

CACHE = REPO / "data" / "yfinance_cache"
OUTDIR_FIG = REPO / "figures"

IS_FRACTION = 0.70                 # identical to H16 / H23
SCHEME_D = (0.0, 1.0, 3.0)         # bullish / neutral / bearish
SHIP_FLOOR = 3.0
PER_TRADE_FLOOR = 2.5
GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42

PAIRS = {
    "GBPUSD": CACHE / "GBPUSD_X_daily.csv",
    "NZDUSD": CACHE / "NZDUSD_X_daily.csv",
}


# ---------------------------------------------------------------------------
# OOS trade-list reconstruction — identical engine path to H23/H16
# ---------------------------------------------------------------------------

def oos_records(csv: pathlib.Path) -> tuple[list[rm.TradeRecord], pd.Timestamp,
                                             pd.Timestamp]:
    df = pd.read_csv(csv, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    is_end = int(len(df) * IS_FRACTION)
    df_oos = df.iloc[is_end:]
    dr = indicators.add_rsi(df_oos, period=14)
    trades = position_sizing.fib_long_at_p1(
        dr, rsi_col="rsi14", cfg=PatternConfig(m_inner_threshold=50.0))
    bias = fld.fld_bias(dr, cycles=(10, 20, 40))
    bull_m, neut_m, bear_m = SCHEME_D
    recs: list[rm.TradeRecord] = []
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        ets = dr.index[t.entry_idx]
        lbl = bias.loc[ets, "bias_label"] if ets in bias.index else "unknown"
        mult = bull_m if lbl == "bullish" else bear_m if lbl == "bearish" else neut_m
        if mult == 0:
            continue
        recs.append(rm.TradeRecord(
            entry_date=pd.Timestamp(ets),
            exit_date=pd.Timestamp(dr.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    return recs, df_oos.index[0], df_oos.index[-1]


def sortino_of(recs: list[rm.TradeRecord]) -> float:
    if len(recs) < 2:
        return float("nan")
    eq = rm.build_equity_curve(recs, initial_capital=1.0, risk_per_trade=0.01)
    return rm.sortino(eq)


# ---------------------------------------------------------------------------
# Test 1 — bootstrap
# ---------------------------------------------------------------------------

def bootstrap(recs: list[rm.TradeRecord]) -> dict:
    rng = np.random.RandomState(BOOT_SEED)
    np.random.seed(BOOT_SEED)  # belt-and-braces per brief
    n = len(recs)
    finite: list[float] = []
    decision_vals = np.empty(N_BOOT, dtype=float)  # nan -> 0 for the decision
    for b in range(N_BOOT):
        idx = rng.randint(0, n, size=n)
        s = sortino_of([recs[i] for i in idx])
        if np.isfinite(s):
            finite.append(s)
            decision_vals[b] = s
        else:
            decision_vals[b] = 0.0
    finite_arr = np.array(finite) if finite else np.array([np.nan])
    return {
        "n_boot": N_BOOT,
        "nan_rate": float(1.0 - len(finite) / N_BOOT),
        "p5_decision": float(np.percentile(decision_vals, 5)),
        "p50_decision": float(np.percentile(decision_vals, 50)),
        "p95_decision": float(np.percentile(decision_vals, 95)),
        "p5_finite": float(np.percentile(finite_arr, 5)),
        "p50_finite": float(np.percentile(finite_arr, 50)),
        "p95_finite": float(np.percentile(finite_arr, 95)),
        "_dist": decision_vals,
    }


# ---------------------------------------------------------------------------
# Test 2 — rolling-window stability
# ---------------------------------------------------------------------------

def rolling_windows(recs: list[rm.TradeRecord], oos_start: pd.Timestamp,
                    oos_end: pd.Timestamp) -> dict:
    span = (oos_end - oos_start).days
    win = pd.Timedelta(days=int(span * 0.50))
    starts_frac = np.linspace(0.0, 0.5, 4)
    windows = []
    for f in starts_frac:
        ws = oos_start + pd.Timedelta(days=int(span * f))
        we = ws + win
        sub = [r for r in recs if ws <= r.entry_date <= we]
        s = sortino_of(sub)
        windows.append({
            "start": ws.date().isoformat(),
            "end": we.date().isoformat(),
            "n_trades": len(sub),
            "sortino": None if np.isnan(s) else round(float(s), 3),
        })
    n_pass = sum(1 for w in windows
                 if w["sortino"] is not None and w["sortino"] >= SHIP_FLOOR)
    vals = [w["sortino"] for w in windows if w["sortino"] is not None]
    return {
        "window_days": int(win.days),
        "windows": windows,
        "n_ge_floor": n_pass,
        "min": float(np.min(vals)) if vals else None,
        "max": float(np.max(vals)) if vals else None,
        "std": float(np.std(vals)) if len(vals) > 1 else None,
    }


# ---------------------------------------------------------------------------
# Test 3 — trade clustering (Gini + 30-day profit share)
# ---------------------------------------------------------------------------

def gini(values: np.ndarray) -> float:
    """Classic Gini via sorted-rank formula. Well-defined for mixed signs;
    interpreted here as concentration of per-trade contribution."""
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    s = x.sum()
    if n == 0 or s == 0:
        return float("nan")
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * x)) / (n * s) - (n + 1.0) / n)


def clustering(recs: list[rm.TradeRecord]) -> dict:
    contrib = np.array([r.r_multiple * r.multiplier for r in recs])
    g_contrib = gini(contrib)
    pos = np.clip(contrib, 0, None)
    g_profit = gini(pos) if pos.sum() > 0 else float("nan")

    # single best 30-day window profit share (by exit date, the realization)
    total_profit = pos.sum()
    best_share = 0.0
    if total_profit > 0:
        exits = pd.Series(pos, index=[r.exit_date for r in recs]).sort_index()
        for ts in exits.index:
            w = exits[(exits.index >= ts) &
                      (exits.index < ts + pd.Timedelta(days=30))].sum()
            best_share = max(best_share, w / total_profit)
    return {
        "gini_contribution": None if np.isnan(g_contrib) else round(g_contrib, 4),
        "gini_profit_only": None if np.isnan(g_profit) else round(g_profit, 4),
        "single_30d_window_profit_share": round(float(best_share), 4),
        "flag_cluster_dependent": (not np.isnan(g_contrib)) and g_contrib > GINI_MAX,
    }


# ---------------------------------------------------------------------------
# Test 4 — per-trade sensitivity
# ---------------------------------------------------------------------------

def per_trade_sensitivity(recs: list[rm.TradeRecord]) -> dict:
    out = []
    for i in range(len(recs)):
        rem = [r for j, r in enumerate(recs) if j != i]
        s = sortino_of(rem)
        out.append((i, s))
    finite = [(i, s) for i, s in out if np.isfinite(s)]
    if finite:
        min_i, min_s = min(finite, key=lambda t: t[1])
    else:
        min_i, min_s = out[0][0], float("nan")
    dropped = recs[min_i]
    return {
        "min_sortino": None if np.isnan(min_s) else round(float(min_s), 3),
        "min_drop_trade": {
            "entry": dropped.entry_date.date().isoformat(),
            "exit": dropped.exit_date.date().isoformat(),
            "r_multiple": round(dropped.r_multiple, 4),
            "multiplier": dropped.multiplier,
        },
        "all_nan": not finite,
        "per_trade": [
            {"dropped_entry": recs[i].entry_date.date().isoformat(),
             "sortino": None if not np.isfinite(s) else round(float(s), 3)}
            for i, s in out
        ],
    }


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

def decide(boot: dict, roll: dict, clus: dict, sens: dict) -> tuple[str, dict]:
    c1 = boot["p5_decision"] >= SHIP_FLOOR
    c2 = roll["n_ge_floor"] >= 3
    c3 = (clus["gini_contribution"] is not None
          and clus["gini_contribution"] <= GINI_MAX)
    c4 = (sens["min_sortino"] is not None
          and sens["min_sortino"] >= PER_TRADE_FLOOR)
    conds = {
        "bootstrap_p5>=+3.0": c1,
        ">=3/4 rolling>=+3.0": c2,
        "Gini<=0.7": c3,
        "per_trade_min>=+2.5": c4,
    }
    n_hold = sum(conds.values())
    if n_hold == 4:
        verdict = "SOLID_GO"
    elif n_hold in (2, 3):
        verdict = "THIN_GO"
    else:
        verdict = "DOWNGRADE_SWEEP"
    return verdict, {"conditions": conds, "n_hold": n_hold}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("H24 — OOS robustness pass: GBPUSD, NZDUSD (thin GO from H23)")
    print("=" * 78)

    results: dict[str, dict] = {}
    for sym, csv in PAIRS.items():
        recs, oos0, oos1 = oos_records(csv)
        base_s = sortino_of(recs)
        print(f"\n--- {sym} --- OOS {oos0.date()}->{oos1.date()} "
              f"| {len(recs)} trades | baseline Sortino {base_s:+.2f}")
        for r in recs:
            print(f"   {r.entry_date.date()} -> {r.exit_date.date()}  "
                  f"R={r.r_multiple:+.3f} x{r.multiplier} "
                  f"contrib={r.r_multiple*r.multiplier:+.2f}")

        boot = bootstrap(recs)
        roll = rolling_windows(recs, oos0, oos1)
        clus = clustering(recs)
        sens = per_trade_sensitivity(recs)
        verdict, dmeta = decide(boot, roll, clus, sens)

        print(f"  [1] bootstrap N={boot['n_boot']} seed={BOOT_SEED}: "
              f"p5={boot['p5_decision']:+.2f} p50={boot['p50_decision']:+.2f} "
              f"p95={boot['p95_decision']:+.2f} (nan-rate {boot['nan_rate']:.1%}; "
              f"finite p5={boot['p5_finite']:+.2f})")
        print(f"  [2] rolling win={roll['window_days']}d: "
              f"{[w['sortino'] for w in roll['windows']]} "
              f"-> {roll['n_ge_floor']}/4 >= +3.0")
        print(f"  [3] Gini(contrib)={clus['gini_contribution']} "
              f"Gini(profit)={clus['gini_profit_only']} "
              f"30d-profit-share={clus['single_30d_window_profit_share']:.0%} "
              f"cluster_flag={clus['flag_cluster_dependent']}")
        print(f"  [4] per-trade min Sortino={sens['min_sortino']} "
              f"(drop {sens['min_drop_trade']['entry']} "
              f"R={sens['min_drop_trade']['r_multiple']:+.2f}"
              f"x{sens['min_drop_trade']['multiplier']})")
        print(f"  CONDITIONS {dmeta['conditions']} -> {dmeta['n_hold']}/4")
        print(f"  ==> VERDICT: {verdict}")

        results[sym] = {
            "oos_window": [oos0.date().isoformat(), oos1.date().isoformat()],
            "n_trades": len(recs),
            "baseline_sortino": round(float(base_s), 3),
            "trades": [
                {"entry": r.entry_date.date().isoformat(),
                 "exit": r.exit_date.date().isoformat(),
                 "r_multiple": round(r.r_multiple, 4),
                 "multiplier": r.multiplier,
                 "contribution": round(r.r_multiple * r.multiplier, 4)}
                for r in recs
            ],
            "bootstrap": {k: v for k, v in boot.items() if k != "_dist"},
            "rolling": roll,
            "clustering": clus,
            "sensitivity": {k: v for k, v in sens.items() if k != "per_trade"},
            "sensitivity_per_trade": sens["per_trade"],
            "verdict": verdict,
            "decision_detail": dmeta,
            "_boot_dist": boot["_dist"],
        }

    # ---- Figure 14: bootstrap distributions ----
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, sym in zip(axes, PAIRS):
        d = results[sym]["_boot_dist"]
        ax.hist(d, bins=60, color="#377eb8", alpha=0.8, edgecolor="white",
                linewidth=0.2)
        b = results[sym]["bootstrap"]
        ax.axvline(SHIP_FLOOR, color="green", linestyle="--", linewidth=1.6,
                   label="ship-floor +3.0")
        ax.axvline(b["p5_decision"], color="red", linestyle="-", linewidth=1.4,
                   label=f"p5 {b['p5_decision']:+.2f}")
        ax.axvline(b["p50_decision"], color="black", linestyle=":",
                   linewidth=1.2, label=f"p50 {b['p50_decision']:+.2f}")
        ax.set_title(f"{sym} — bootstrap Sortino (N={N_BOOT}, seed {BOOT_SEED})\n"
                     f"{results[sym]['verdict']} · nan→0 mapped "
                     f"({b['nan_rate']:.0%} degenerate)", fontsize=10)
        ax.set_xlabel("Sortino (resampled OOS)")
        ax.set_ylabel("count")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    plt.tight_layout()
    f14 = OUTDIR_FIG / "14_robustness_bootstrap.png"
    plt.savefig(f14, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {f14}")

    # ---- Figure 15: rolling-window Sortinos ----
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = {"GBPUSD": "#d62728", "NZDUSD": "#17becf"}
    for sym in PAIRS:
        roll = results[sym]["rolling"]
        xs = [pd.Timestamp(w["start"]) +
              (pd.Timestamp(w["end"]) - pd.Timestamp(w["start"])) / 2
              for w in roll["windows"]]
        ys = [w["sortino"] if w["sortino"] is not None else np.nan
              for w in roll["windows"]]
        ax.plot(xs, ys, "o-", color=colors[sym], linewidth=1.6, markersize=8,
                label=f"{sym} ({results[sym]['verdict']})")
        for x, y, w in zip(xs, ys, roll["windows"]):
            ax.annotate(f"n={w['n_trades']}", (x, y if not np.isnan(y) else 0),
                        textcoords="offset points", xytext=(0, 8),
                        fontsize=8, ha="center")
    ax.axhline(SHIP_FLOOR, color="green", linestyle="--", linewidth=1.4,
               label="ship-floor +3.0")
    ax.axhline(0, color="black", linewidth=0.5, alpha=0.4)
    ax.set_title("H24 — rolling-window OOS Sortino (window = 50% of OOS span,\n"
                 "4 windows at start-fractions 0 / 1/6 / 1/3 / 1/2)",
                 fontsize=11, pad=10)
    ax.set_xlabel("window midpoint")
    ax.set_ylabel("Sortino")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    plt.tight_layout()
    f15 = OUTDIR_FIG / "15_robustness_rolling.png"
    plt.savefig(f15, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"Wrote {f15}")

    dump = {
        "seed": BOOT_SEED, "n_boot": N_BOOT, "is_fraction": IS_FRACTION,
        "ship_floor": SHIP_FLOOR, "per_trade_floor": PER_TRADE_FLOOR,
        "gini_max": GINI_MAX,
        "pairs": {
            sym: {k: v for k, v in r.items() if k != "_boot_dist"}
            for sym, r in results.items()
        },
    }
    jp = REPO / "results" / "_h24_run.json"
    jp.write_text(json.dumps(dump, indent=2, default=str))
    print(f"Wrote {jp}\nDONE.")


if __name__ == "__main__":
    main()
