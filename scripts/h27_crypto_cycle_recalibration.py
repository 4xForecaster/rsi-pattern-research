#!/usr/bin/env python3
"""H27 — Crypto cycle/cadence recalibration (the lever-identification experiment).

H26 left a sharp puzzle: the M-P1 LONG *edge* looked excellent on crypto
(ETH OOS Sortino +12.55, no IS->OOS degradation) yet every crypto major
was NO-GO — apparently on trade count. The teed-up hypothesis was
"recalibrate the FLD cycle ladder for crypto's faster structure."

H27 FALSIFIES that hypothesis up front and pivots to the true lever:

  FINDING 1 (FLD ladder is a NULL lever). The M-top trade UNIVERSE is set
  by RSI M-detection, NOT by the FLD ladder — the ladder only drives the
  Scheme-D bias multiplier (0/1/3). Probed across (10,20,40), (5,10,20),
  (8,16,32), (6,12,24): the OOS universe is INVARIANT (BTC 24, ETH 16,
  SOL 7). No ladder can lift crypto to the OOS-trade floors (ETH maxes at
  8 surviving trades < the 10-trade NO-GO floor under EVERY ladder). The
  cycle ladder is not the constraint.

  FINDING 2 (detection CADENCE is the real lever). Crypto's recon shows
  dominant fast-cycle energy (~5-8 bars) that FX lacks. Scaling the
  DETECTOR cadence (shorter RSI period + proportionally scaled M timing
  windows) grows the universe and, for ETH/SOL, preserves/【improves the
  OOS edge. That is what H27 tests rigorously.

OVERFITTING DISCLOSURE (load-bearing honesty): the cadence candidates
below were glimpsed against OOS during exploratory probing. To stay
honest about that:
  * the PRIMARY crypto cadence is chosen by THEORY/recon, not by OOS
    performance, and is the MODERATE option (RSI9), deliberately NOT the
    best-OOS option (RSI7) — anti-cherry-pick guard;
  * RSI7 is reported only as a sensitivity row;
  * any cadence that clears GO is treated as a FORWARD-TEST CANDIDATE
    (enabled:false, robustness-gated), NOT a live ship, precisely because
    the OOS is no longer pristine and crypto history is short.

Protocol otherwise identical to H23/H26: verbatim run_one engine,
70/30 split by bars, OOS load-bearing, locked rules, seed=42.
Decision is reported under BOTH the STRICT (OOS-trade) rule [primary,
H26-consistent] and the PRAGMATIC (full-trade floor) rule [secondary],
because — unlike H26 — the cadence change makes the two diverge.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import periodogram

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import indicators, fld, position_sizing
from rsi_pattern.patterns import PatternConfig
from rsi_pattern import risk_metrics as rm

CACHE = REPO / "data" / "yfinance_cache"
OUTDIR_FIG = REPO / "figures"

IS_FRACTION = 0.70
SCHEME_D = (0.0, 1.0, 3.0)
FLD_CYCLES = (10, 20, 40)     # FINDING 1: ladder is null → held fixed
SHIP_FLOOR = 3.0
PER_TRADE_FLOOR = 2.5
GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42

SYMS = {"BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD"}

# Pre-registered FLD ladders for the null-lever demonstration (FINDING 1).
LADDER_GRID = [(10, 20, 40), (5, 10, 20), (8, 16, 32), (6, 12, 24)]


@dataclass(frozen=True)
class Cadence:
    name: str
    rsi_period: int
    max_span: int
    max_completion: int
    min_peak_distance: int
    role: str  # "baseline" | "primary" | "sensitivity"


# Pre-registered cadences. Windows scale ~ rsi_period/14 (theory: crypto's
# faster cyclicity ⇒ shorter oscillator + proportionally shorter pattern
# windows). PRIMARY = moderate RSI9 (NOT the best-OOS RSI7).
CADENCES = [
    Cadence("D0_RSI14_baseline", 14, 30, 30, 3, "baseline"),
    Cadence("D1_RSI9_crypto",     9, 19, 19, 2, "primary"),
    Cadence("D2_RSI7_sensitivity", 7, 15, 15, 2, "sensitivity"),
]


def load(sym_ticker: str) -> pd.DataFrame:
    cp = CACHE / f"{sym_ticker.replace('=', '_').replace('^', '')}_daily.csv"
    df = pd.read_csv(cp, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def split(df: pd.DataFrame):
    e = int(len(df) * IS_FRACTION)
    return df.iloc[:e], df.iloc[e:]


# ---------------------------------------------------------------------------
# Engine (verbatim run_one, parameterized by cadence + ladder)
# ---------------------------------------------------------------------------

def run_one(df: pd.DataFrame, cad: Cadence, cycles=FLD_CYCLES) -> dict:
    dr = indicators.add_rsi(df, period=cad.rsi_period)
    cfg = PatternConfig(m_inner_threshold=50.0, max_span_bars=cad.max_span,
                        max_completion_bars=cad.max_completion,
                        min_peak_distance_bars=cad.min_peak_distance)
    trades = position_sizing.fib_long_at_p1(dr, rsi_col=f"rsi{cad.rsi_period}", cfg=cfg)
    bias = fld.fld_bias(dr, cycles=cycles)
    bull_m, neut_m, bear_m = SCHEME_D
    recs, universe = [], 0
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        universe += 1
        ets = dr.index[t.entry_idx]
        lbl = bias.loc[ets, "bias_label"] if ets in bias.index else "unknown"
        mult = bull_m if lbl == "bullish" else bear_m if lbl == "bearish" else neut_m
        if mult == 0:
            continue
        recs.append(rm.TradeRecord(entry_date=pd.Timestamp(ets),
                                   exit_date=pd.Timestamp(dr.index[t.exit_idx]),
                                   r_multiple=float(t.r_multiple), multiplier=float(mult)))
    eq = rm.build_equity_curve(recs, 1.0, 0.01)
    return {"universe": universe, "trades": len(recs),
            "sortino": float(rm.sortino(eq)), "max_dd": float(rm.max_drawdown(eq)),
            "equity": eq, "records": recs}


def decide_strict(oos: dict) -> str:
    s, n = oos["sortino"], oos["trades"]
    if np.isnan(s):
        return "NO-GO"
    if s >= SHIP_FLOOR and n >= 30:
        return "GO"
    if s < 1.0 or n < 10:
        return "NO-GO"
    return "SWEEP"


def decide_pragmatic(oos: dict, full: dict) -> str:
    s, fn = oos["sortino"], full["trades"]
    if np.isnan(s):
        return "NO-GO"
    if s >= SHIP_FLOOR and fn >= 30:
        return "GO"
    if s < 1.0 or fn < 10:
        return "NO-GO"
    return "SWEEP"


# ---------------------------------------------------------------------------
# Recon (IS-only periodogram) — theory input, not performance
# ---------------------------------------------------------------------------

def recon_is(df_is: pd.DataFrame) -> dict:
    lr = np.log(df_is["close"]).diff().dropna().values
    f, p = periodogram(lr - lr.mean(), window="hann")
    per = np.full_like(f, np.nan)
    per[f > 0] = 1.0 / f[f > 0]
    band = (per >= 3) & (per <= 160)
    order = np.argsort(p[band])[::-1][:8]
    return {"dominant_periods_bars": sorted(round(float(x), 1) for x in per[band][order]),
            "is_bars": len(df_is)}


# ---------------------------------------------------------------------------
# H24 robustness
# ---------------------------------------------------------------------------

def _sortino(recs):
    if len(recs) < 2:
        return float("nan")
    return rm.sortino(rm.build_equity_curve(recs, 1.0, 0.01))


def _gini(v):
    x = np.sort(np.asarray(v, float)); n, s = len(x), x.sum()
    if n == 0 or s == 0:
        return float("nan")
    return float((2 * np.sum(np.arange(1, n + 1) * x)) / (n * s) - (n + 1) / n)


def robustness(recs, oos0, oos1) -> dict:
    rng = np.random.RandomState(BOOT_SEED); np.random.seed(BOOT_SEED)
    n = len(recs); dist = np.empty(N_BOOT)
    for b in range(N_BOOT):
        sv = _sortino([recs[i] for i in rng.randint(0, n, n)])
        dist[b] = sv if np.isfinite(sv) else 0.0
    p5 = float(np.percentile(dist, 5))
    span = max((oos1 - oos0).days, 1); win = pd.Timedelta(days=int(span * 0.5))
    wins = [_sortino([r for r in recs if oos0 + pd.Timedelta(days=int(span * f)) <= r.entry_date
                      <= oos0 + pd.Timedelta(days=int(span * f)) + win])
            for f in np.linspace(0, 0.5, 4)]
    n_ge = sum(1 for w in wins if np.isfinite(w) and w >= SHIP_FLOOR)
    g = _gini(np.array([r.r_multiple * r.multiplier for r in recs]))
    drops = [_sortino([r for j, r in enumerate(recs) if j != i]) for i in range(n)]
    fd = [d for d in drops if np.isfinite(d)]; mn = min(fd) if fd else float("nan")
    c = [p5 >= SHIP_FLOOR, n_ge >= 3, (not np.isnan(g)) and g <= GINI_MAX,
         (not np.isnan(mn)) and mn >= PER_TRADE_FLOOR]
    hold = sum(c)
    return {"boot_p5": round(p5, 3), "rolling": [None if not np.isfinite(w) else round(float(w), 3) for w in wins],
            "n_rolling_ge": n_ge, "gini": None if np.isnan(g) else round(g, 4),
            "per_trade_min": None if np.isnan(mn) else round(mn, 3), "n_hold": hold,
            "verdict": "SOLID_GO" if hold == 4 else "THIN_GO" if hold in (2, 3) else "DOWNGRADE_SWEEP"}


def main() -> None:
    print("=" * 82)
    print("H27 — Crypto cycle/cadence recalibration")
    print("=" * 82)
    data = {s: load(t) for s, t in SYMS.items()}

    # FINDING 1 — FLD ladder is a null lever (universe invariance)
    print("\nFINDING 1 — FLD ladder null-lever check (OOS universe must be ladder-invariant)")
    f1 = {}
    for s, df in data.items():
        _, oos = split(df)
        row = {}
        for L in LADDER_GRID:
            r = run_one(oos, CADENCES[0], cycles=L)
            row[str(L)] = {"universe": r["universe"], "trades": r["trades"],
                           "sortino": round(r["sortino"], 2)}
        f1[s] = row
        us = {v["universe"] for v in row.values()}
        print(f"  {s}: universe across ladders = {us} "
              f"({'INVARIANT ✓' if len(us) == 1 else 'VARIES'}) | "
              f"trades/sortino: " + " ".join(f"{k}->{v['trades']}t/{v['sortino']:+.2f}"
                                              for k, v in row.items()))

    # Recon (IS only)
    print("\nRECON (IS-only periodogram, theory input):")
    recon = {}
    for s, df in data.items():
        is_df, _ = split(df)
        recon[s] = recon_is(is_df)
        print(f"  {s}: dominant IS periods (bars) = {recon[s]['dominant_periods_bars']}")

    # FINDING 2 — cadence experiment
    print("\nFINDING 2 — detection cadence sweep (FLD held at (10,20,40))")
    print("Faithfulness: D0 must reproduce H26 (BTC 5t/+0.65, ETH 7t/+12.55, SOL 4t/-0.45)")
    results = {}
    for s, df in data.items():
        is_df, oos = split(df)
        results[s] = {"oos_window": [oos.index[0].date().isoformat(),
                                     oos.index[-1].date().isoformat(), len(oos)], "cadences": {}}
        print(f"\n--- {s} --- OOS {oos.index[0].date()}->{oos.index[-1].date()} ({len(oos)} bars)")
        for cad in CADENCES:
            full = run_one(df, cad)
            o = run_one(oos, cad)
            ds = decide_strict(o)
            dp = decide_pragmatic(o, full)
            rob = None
            if "GO" in (ds, dp) and o["trades"] >= 10:
                rob = robustness(o["records"], oos.index[0], oos.index[-1])
            results[s]["cadences"][cad.name] = {
                "role": cad.role, "rsi": cad.rsi_period,
                "oos_universe": o["universe"], "oos_trades": o["trades"],
                "oos_sortino": round(o["sortino"], 3), "oos_max_dd": round(o["max_dd"], 4),
                "full_trades": full["trades"], "full_sortino": round(full["sortino"], 3),
                "decision_strict": ds, "decision_pragmatic": dp, "robustness": rob,
                "_equity": full["equity"]}
            tag = " <PRIMARY>" if cad.role == "primary" else (" <baseline>" if cad.role == "baseline" else "")
            print(f"  {cad.name:20s}{tag:10s} OOS univ={o['universe']:>2} trades={o['trades']:>2} "
                  f"Sortino={o['sortino']:>+7.2f} | STRICT={ds:6s} PRAGMATIC={dp:6s}"
                  + (f" | robust {rob['verdict']}({rob['n_hold']}/4)" if rob else ""))

    # Figures
    OUTDIR_FIG.mkdir(exist_ok=True)
    # Fig 20: recon periodograms (IS) with cadence markers
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for ax, (s, df) in zip(axes, data.items()):
        is_df, _ = split(df)
        lr = np.log(is_df["close"]).diff().dropna().values
        f, p = periodogram(lr - lr.mean(), window="hann")
        per = np.where(f > 0, 1.0 / np.where(f == 0, np.nan, f), np.nan)
        m = (per >= 3) & (per <= 120)
        ax.semilogy(per[m], p[m], color="#f7931a", lw=1.0)
        for c, lab in [(14, "RSI14"), (9, "RSI9*"), (7, "RSI7")]:
            ax.axvline(c, ls="--", lw=1.0, alpha=0.7,
                       color="#555" if c == 14 else ("#2ca02c" if c == 9 else "#d62728"),
                       label=lab)
        ax.set_title(f"{s} IS periodogram", fontsize=10)
        ax.set_xlabel("period (bars)"); ax.set_ylabel("power"); ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("H27 fig20 — crypto IS spectral structure (theory input; *RSI9 = pre-registered primary)",
                 fontsize=11)
    plt.tight_layout()
    f20 = OUTDIR_FIG / "20_crypto_cycle_recon.png"
    plt.savefig(f20, dpi=140, bbox_inches="tight"); plt.close()
    print(f"\nWrote {f20}")

    # Fig 21: OOS universe + OOS Sortino by cadence
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))
    xs = np.arange(len(SYMS)); w = 0.26
    cols = {"D0_RSI14_baseline": "#999", "D1_RSI9_crypto": "#2ca02c", "D2_RSI7_sensitivity": "#d62728"}
    for i, cad in enumerate(CADENCES):
        uni = [results[s]["cadences"][cad.name]["oos_universe"] for s in SYMS]
        srt = [results[s]["cadences"][cad.name]["oos_sortino"] for s in SYMS]
        ax1.bar(xs + (i - 1) * w, uni, w, label=cad.name, color=cols[cad.name], edgecolor="black", lw=0.4)
        ax2.bar(xs + (i - 1) * w, [min(max(v, -3), 14) for v in srt], w, label=cad.name,
                color=cols[cad.name], edgecolor="black", lw=0.4)
    ax1.axhline(30, color="green", ls="--", lw=1.2, label="GO OOS-trade floor (30)")
    ax1.axhline(10, color="red", ls=":", lw=1.2, label="NO-GO floor (10)")
    ax1.set_xticks(xs); ax1.set_xticklabels(list(SYMS)); ax1.set_ylabel("OOS universe (M-tops)")
    ax1.set_title("OOS trade universe by cadence\n(grows with shorter RSI — the real lever)", fontsize=10)
    ax1.legend(fontsize=7.5); ax1.grid(True, axis="y", alpha=0.3)
    ax2.axhline(SHIP_FLOOR, color="green", ls="--", lw=1.2, label="GO Sortino +3.0")
    ax2.axhline(1.0, color="red", ls=":", lw=1.2)
    ax2.set_xticks(xs); ax2.set_xticklabels(list(SYMS)); ax2.set_ylabel("OOS Sortino (clipped [-3,14])")
    ax2.set_title("OOS Sortino by cadence", fontsize=10)
    ax2.legend(fontsize=7.5); ax2.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    f21 = OUTDIR_FIG / "21_crypto_cadence_sweep.png"
    plt.savefig(f21, dpi=140, bbox_inches="tight"); plt.close()
    print(f"Wrote {f21}")

    dump = {"seed": BOOT_SEED, "is_fraction": IS_FRACTION, "fld_cycles_fixed": FLD_CYCLES,
            "finding1_ladder_null": f1, "recon_is": recon,
            "cadences": [c.__dict__ for c in CADENCES],
            "results": {s: {"oos_window": r["oos_window"],
                            "cadences": {k: {kk: vv for kk, vv in v.items() if kk != "_equity"}
                                         for k, v in r["cadences"].items()}}
                        for s, r in results.items()}}
    (REPO / "results" / "_h27_run.json").write_text(json.dumps(dump, indent=2, default=str))
    print(f"Wrote {REPO/'results'/'_h27_run.json'}")

    # GO accounting under PRIMARY (STRICT) rule
    primary_go = [s for s in SYMS
                  if results[s]["cadences"]["D1_RSI9_crypto"]["decision_strict"] == "GO"]
    print(f"\nPRIMARY (RSI9, STRICT-rule) GO count: {len(primary_go)} {primary_go}")
    print("DONE.")


if __name__ == "__main__":
    main()
