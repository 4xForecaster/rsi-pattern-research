#!/usr/bin/env python3
"""H25 — V-pattern SHORT cross-symbol expansion + directional comparison.

Hypothesis: the M-P1 LONG stack works where USD / pair-base trends up and
fails (structurally) where the pair trends down. A symmetric V-floor
breach SHORT should pick up the inverse opportunities and may turn
M-LONG structural NO-GOs/SWEEPs into V-SHORT GOs.

Pipeline parity:
  * V-SHORT  : rsi_pattern.strategies_vshort.run_vshort  (reuses the
               H8-faithful position_sizing.fib_short_at_v_floor engine)
  * M-LONG   : the verbatim H23/H16 run_one (loose-M, fib_long_at_p1,
               FLD 10/20/40, Scheme D 0/1/3) — recomputed here for the
               same 9 pairs so the directional matrix is apples-to-apples.

Faithfulness gate (runs FIRST, aborts on failure): DXY daily V-floor
SHORT mean R-multiple must reproduce the H8 anchor +0.48.

70/30 split by bars (H16/H23 protocol). OOS Sortino load-bearing;
full-sample 30-trade floor. Locked GO rule: GO = OOS Sortino ≥ +3.0 AND
full trades ≥ 30; NO-GO = OOS Sortino < +1.0 OR full trades < 10; else
SWEEP. Any thin V-SHORT GO gets the H24 4-test robustness pass.
"""
from __future__ import annotations

import json
import pathlib
import sys
import warnings
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
from rsi_pattern import strategies_vshort as vs

CACHE = REPO / "data" / "yfinance_cache"
CACHE.mkdir(parents=True, exist_ok=True)
OUTDIR_FIG = REPO / "figures"

IS_FRACTION = 0.70
SCHEME_D = (0.0, 1.0, 3.0)
SHIP_FLOOR = 3.0
PER_TRADE_FLOOR = 2.5
GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42
YF_END = "2026-05-19"
H8_ANCHOR = 0.48
H8_TOL = 0.05

# DXY = BarChart CSV (reproduces H8/H12 anchors). FX via yfinance, cached.
# USDMXN/USDCHF use the H15 tickers (MXN=X / CHF=X) for continuity.
YF_TICKERS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X", "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X",
    "USDMXN": "MXN=X", "USDCHF": "CHF=X",
}
ORDER = ["DXY", "EURUSD", "GBPUSD", "USDJPY", "USDCAD",
         "AUDUSD", "NZDUSD", "USDMXN", "USDCHF"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_yf(ticker: str) -> pd.DataFrame:
    cp = CACHE / f"{ticker.replace('=', '_').replace('^', '')}_daily.csv"
    if cp.exists():
        df = pd.read_csv(cp, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
        return df
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import yfinance as yf
        raw = yf.download(ticker, start="1990-01-01", end=YF_END,
                          progress=False, auto_adjust=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance empty for {ticker!r}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    df = pd.DataFrame({
        "open": pd.to_numeric(raw["Open"], errors="coerce"),
        "high": pd.to_numeric(raw["High"], errors="coerce"),
        "low": pd.to_numeric(raw["Low"], errors="coerce"),
        "close": pd.to_numeric(raw["Close"], errors="coerce"),
        "volume": pd.to_numeric(raw.get("Volume", 0), errors="coerce"),
    })
    df.index = pd.to_datetime(raw.index, utc=True)
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_index()
    if len(df) < 250:
        raise RuntimeError(f"{ticker}: only {len(df)} bars — skip, no fake")
    df.to_csv(cp)
    return df


def load_dxy() -> pd.DataFrame:
    from rsi_pattern import data as dm
    dm.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return dm.load_dxy("daily")


# ---------------------------------------------------------------------------
# M-LONG engine — verbatim H23/H16 run_one (for the directional matrix)
# ---------------------------------------------------------------------------

def mlong_metrics(df: pd.DataFrame) -> dict:
    dr = indicators.add_rsi(df, period=14)
    trades = position_sizing.fib_long_at_p1(
        dr, rsi_col="rsi14", cfg=PatternConfig(m_inner_threshold=50.0))
    bias = fld.fld_bias(dr, cycles=(10, 20, 40))
    bull_m, neut_m, bear_m = SCHEME_D
    recs = []
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        ets = dr.index[t.entry_idx]
        lbl = bias.loc[ets, "bias_label"] if ets in bias.index else "unknown"
        mult = bull_m if lbl == "bullish" else bear_m if lbl == "bearish" else neut_m
        if mult == 0:
            continue
        recs.append(rm.TradeRecord(entry_date=pd.Timestamp(ets),
                                   exit_date=pd.Timestamp(dr.index[t.exit_idx]),
                                   r_multiple=float(t.r_multiple),
                                   multiplier=float(mult)))
    eq = rm.build_equity_curve(recs, 1.0, 0.01)
    return {"trades": len(recs), "sortino": rm.sortino(eq),
            "max_dd": rm.max_drawdown(eq), "records": recs, "equity": eq}


# ---------------------------------------------------------------------------
# Decision + split
# ---------------------------------------------------------------------------

def split_70_30(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    e = int(len(df) * IS_FRACTION)
    return df.iloc[:e], df.iloc[e:]


def go_no_go(oos_sortino: float, full_trades: int, oos_trades: int) -> tuple[str, str]:
    s = oos_sortino
    if np.isnan(s):
        return "NO-GO", f"OOS Sortino undefined (OOS n={oos_trades})"
    if s >= SHIP_FLOOR and full_trades >= 30:
        return "GO", (f"OOS Sortino {s:+.2f}≥3.0 & full {full_trades}≥30 "
                      f"(OOS n={oos_trades})")
    if s < 1.0 or full_trades < 10:
        return "NO-GO", f"OOS Sortino {s:+.2f}<1.0 or full {full_trades}<10"
    return "SWEEP", f"OOS Sortino {s:+.2f} in [1,3) / thin (full={full_trades}, OOS={oos_trades})"


# ---------------------------------------------------------------------------
# H24-style robustness (only for thin V-SHORT GOs)
# ---------------------------------------------------------------------------

def _sortino_of(recs: list) -> float:
    if len(recs) < 2:
        return float("nan")
    return rm.sortino(rm.build_equity_curve(recs, 1.0, 0.01))


def _gini(values: np.ndarray) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    s = x.sum()
    if n == 0 or s == 0:
        return float("nan")
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * x)) / (n * s) - (n + 1.0) / n)


def robustness(recs: list, oos0: pd.Timestamp, oos1: pd.Timestamp) -> dict:
    rng = np.random.RandomState(BOOT_SEED)
    np.random.seed(BOOT_SEED)
    n = len(recs)
    dist = np.empty(N_BOOT)
    fin = []
    for b in range(N_BOOT):
        s = _sortino_of([recs[i] for i in rng.randint(0, n, n)])
        dist[b] = s if np.isfinite(s) else 0.0
        if np.isfinite(s):
            fin.append(s)
    p5 = float(np.percentile(dist, 5))
    span = (oos1 - oos0).days
    win = pd.Timedelta(days=int(span * 0.5))
    wins = []
    for f in np.linspace(0.0, 0.5, 4):
        ws = oos0 + pd.Timedelta(days=int(span * f))
        sub = [r for r in recs if ws <= r.entry_date <= ws + win]
        wins.append(_sortino_of(sub))
    n_ge = sum(1 for w in wins if np.isfinite(w) and w >= SHIP_FLOOR)
    contrib = np.array([r.r_multiple * r.multiplier for r in recs])
    g = _gini(contrib)
    drops = [_sortino_of([r for j, r in enumerate(recs) if j != i])
             for i in range(n)]
    fdrops = [d for d in drops if np.isfinite(d)]
    min_drop = min(fdrops) if fdrops else float("nan")
    c1, c2 = p5 >= SHIP_FLOOR, n_ge >= 3
    c3 = (not np.isnan(g)) and g <= GINI_MAX
    c4 = (not np.isnan(min_drop)) and min_drop >= PER_TRADE_FLOOR
    hold = sum([c1, c2, c3, c4])
    verdict = "SOLID_GO" if hold == 4 else "THIN_GO" if hold in (2, 3) else "DOWNGRADE_SWEEP"
    return {"boot_p5": round(p5, 3), "boot_p50": round(float(np.percentile(dist, 50)), 3),
            "rolling": [None if not np.isfinite(w) else round(float(w), 3) for w in wins],
            "n_rolling_ge": n_ge, "gini": None if np.isnan(g) else round(g, 4),
            "per_trade_min": None if np.isnan(min_drop) else round(min_drop, 3),
            "conditions": {"boot_p5>=3": c1, ">=3/4 roll": c2, "gini<=0.7": c3,
                           "per_trade>=2.5": c4}, "n_hold": hold, "verdict": verdict}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 80)
    print("H25 — V-SHORT cross-symbol expansion + M-LONG vs V-SHORT matrix")
    print("=" * 80)

    data: dict[str, pd.DataFrame] = {}
    skipped: dict[str, str] = {}
    try:
        data["DXY"] = load_dxy()
    except Exception as e:  # noqa: BLE001
        skipped["DXY"] = str(e)
    for sym in ORDER:
        if sym == "DXY":
            continue
        try:
            data[sym] = load_yf(YF_TICKERS[sym])
        except Exception as e:  # noqa: BLE001
            skipped[sym] = f"{YF_TICKERS[sym]}: {e}"
            print(f"  [SKIP] {sym}: {e}")

    # ---- Faithfulness gate (FIRST) ----
    print("\nFAITHFULNESS GATE — DXY V-floor SHORT vs H8 anchor +0.48")
    if "DXY" not in data:
        raise SystemExit("DXY data unavailable — cannot run faithfulness gate")
    dxy_mr = vs.faithfulness_mean_r(data["DXY"], spread_bps=2.0)
    ok = abs(dxy_mr - H8_ANCHOR) <= H8_TOL
    print(f"  DXY V-short mean R-multiple = {dxy_mr:+.4f}  "
          f"(anchor {H8_ANCHOR:+.2f} ± {H8_TOL}) -> "
          f"{'PASS — faithful' if ok else 'FAIL'}")
    if not ok:
        raise SystemExit("Faithfulness FAILED — not expanding a broken impl.")

    # ---- Per-pair V-SHORT + M-LONG ----
    print("\nPER-PAIR — V-SHORT (70/30, OOS load-bearing) + M-LONG comparison")
    results: dict[str, dict] = {}
    for sym in ORDER:
        if sym not in data:
            continue
        df = data[sym]
        is_df, oos_df = split_70_30(df)
        vf = vs.run_vshort(df, label=f"{sym} V-SHORT FULL")
        vo = vs.run_vshort(oos_df, label=f"{sym} V-SHORT OOS")
        vi = vs.run_vshort(is_df, label=f"{sym} V-SHORT IS")
        vdec, vrsn = go_no_go(vo.sortino, vf.trades, vo.trades)

        ml_full = mlong_metrics(df)
        ml_oos = mlong_metrics(oos_df)
        mdec, _ = go_no_go(ml_oos["sortino"], ml_full["trades"], ml_oos["trades"])

        rob = None
        if vdec == "GO" and vo.trades < 15:  # thin GO → H24 robustness
            rob = robustness(vo.records, oos_df.index[0], oos_df.index[-1])
            if rob["verdict"] == "DOWNGRADE_SWEEP":
                vdec = "SWEEP"
                vrsn += f" | H24-robustness 0-1/4 -> downgraded ({rob['verdict']})"
            elif rob["verdict"] == "THIN_GO":
                vrsn += f" | H24-robustness 2-3/4 -> THIN GO (stays GO, not live)"
            else:
                vrsn += f" | H24-robustness 4/4 -> SOLID"

        results[sym] = {
            "data_first": df.index[0].date().isoformat(),
            "data_last": df.index[-1].date().isoformat(),
            "data_bars": len(df),
            "oos_window": [oos_df.index[0].date().isoformat(),
                           oos_df.index[-1].date().isoformat(), len(oos_df)],
            "vshort": {"full_trades": vf.trades, "full_sortino": round(float(vf.sortino), 3),
                       "oos_trades": vo.trades, "oos_sortino": round(float(vo.sortino), 3),
                       "is_sortino": round(float(vi.sortino), 3),
                       "oos_max_dd": round(float(vo.max_dd), 4),
                       "bias_counts_full": vf.bias_counts},
            "vshort_decision": vdec, "vshort_reason": vrsn,
            "vshort_robustness": rob,
            "mlong": {"full_trades": ml_full["trades"],
                      "full_sortino": round(float(ml_full["sortino"]), 3),
                      "oos_trades": ml_oos["trades"],
                      "oos_sortino": round(float(ml_oos["sortino"]), 3)},
            "mlong_decision": mdec,
            "_v_equity": vf.equity,
        }
        v, m = results[sym], results[sym]["mlong"]
        print(f"  {sym:7s} | V-SHORT {vdec:6s} OOS S={v['vshort']['oos_sortino']:>+6.2f} "
              f"n={v['vshort']['oos_trades']:>2}/{v['vshort']['full_trades']:>2} | "
              f"M-LONG {results[sym]['mlong_decision']:6s} OOS S={m['oos_sortino']:>+6.2f} "
              f"n={m['oos_trades']:>2}/{m['full_trades']:>2}")

    # ---- Directional matrix ----
    print("\nDIRECTIONAL COMPARISON MATRIX (M-LONG decision  ×  V-SHORT decision)")
    def quad(md: str, vd: str) -> str:
        mg, vg = md == "GO", vd == "GO"
        if mg and vg:
            return "BOTH (regime-aware portfolio)"
        if mg and not vg:
            return "LONG-ONLY (trend-with-USD/base)"
        if vg and not mg:
            return "SHORT-ONLY (trend-against)"
        return "NEITHER (untradeable here)"
    hdr = f"{'Symbol':<8}{'M-LONG':<8}{'V-SHORT':<9}{'M OOS S':>9}{'V OOS S':>9}  Quadrant"
    print(hdr); print("-" * len(hdr))
    for sym in ORDER:
        if sym not in results:
            continue
        r = results[sym]
        print(f"{sym:<8}{r['mlong_decision']:<8}{r['vshort_decision']:<9}"
              f"{r['mlong']['oos_sortino']:>+9.2f}{r['vshort']['oos_sortino']:>+9.2f}"
              f"  {quad(r['mlong_decision'], r['vshort_decision'])}")
        r["quadrant"] = quad(r["mlong_decision"], r["vshort_decision"])

    # ---- Figure 16: 9-pair V-SHORT equity overlay ----
    fig, ax = plt.subplots(figsize=(13, 7))
    palette = {"DXY": "#555555", "EURUSD": "#1f77b4", "GBPUSD": "#d62728",
               "USDJPY": "#2ca02c", "USDCAD": "#9467bd", "AUDUSD": "#ff7f0e",
               "NZDUSD": "#17becf", "USDMXN": "#8c564b", "USDCHF": "#e377c2"}
    for sym in ORDER:
        if sym not in results:
            continue
        eq = results[sym]["_v_equity"]
        ax.plot(eq.index, eq.values, label=f"{sym} ({results[sym]['vshort_decision']})",
                color=palette.get(sym, "#000"),
                linewidth=1.8 if sym == "DXY" else 1.2,
                linestyle="--" if sym == "DXY" else "-")
    ax.axhline(1.0, color="black", linewidth=0.5, alpha=0.4)
    ax.set_title("H25 — V-SHORT full-sample equity (9 pairs, DXY params, no re-tune)\n"
                 "V-floor breach short · SURF Fib · Scheme D (bull0/neu1/bear3) · 1% risk",
                 fontsize=11, pad=10)
    ax.set_xlabel("Date"); ax.set_ylabel("Equity (start = 1.0)")
    ax.grid(True, alpha=0.3); ax.legend(loc="upper left", fontsize=8.5, framealpha=.95)
    plt.tight_layout()
    f16 = OUTDIR_FIG / "16_vshort_equity_curves.png"
    plt.savefig(f16, dpi=140, bbox_inches="tight"); plt.close()
    print(f"\nWrote {f16}")

    # ---- Figure 17: M-LONG vs V-SHORT scatter (OOS Sortino, quadrants) ----
    fig, ax = plt.subplots(figsize=(9.5, 9))
    LIM = 8.0
    def clip(v): return max(-2.0, min(LIM, v)) if np.isfinite(v) else -2.0
    for sym in ORDER:
        if sym not in results:
            continue
        r = results[sym]
        x = clip(r["mlong"]["oos_sortino"]); y = clip(r["vshort"]["oos_sortino"])
        ax.scatter(x, y, s=90, color=palette.get(sym, "#000"),
                   edgecolor="black", linewidth=0.6, zorder=3)
        ax.annotate(sym, (x, y), textcoords="offset points", xytext=(7, 5),
                    fontsize=9, fontweight="bold")
    ax.axvline(SHIP_FLOOR, color="green", ls="--", lw=1.3)
    ax.axhline(SHIP_FLOOR, color="green", ls="--", lw=1.3)
    ax.set_xlim(-2, LIM); ax.set_ylim(-2, LIM)
    ax.text(LIM - 0.1, LIM - 0.1, "BOTH\n(regime portfolio)", ha="right",
            va="top", fontsize=10, color="#2ca02c", fontweight="bold")
    ax.text(-1.9, LIM - 0.1, "SHORT-ONLY\n(trend-against)", ha="left", va="top",
            fontsize=10, color="#1f77b4", fontweight="bold")
    ax.text(LIM - 0.1, -1.9, "LONG-ONLY\n(trend-with)", ha="right", va="bottom",
            fontsize=10, color="#ff7f0e", fontweight="bold")
    ax.text(-1.9, -1.9, "NEITHER\n(untradeable)", ha="left", va="bottom",
            fontsize=10, color="#d62728", fontweight="bold")
    ax.set_xlabel("M-LONG OOS Sortino  (≥ +3.0 = GO)")
    ax.set_ylabel("V-SHORT OOS Sortino  (≥ +3.0 = GO)")
    ax.set_title("H25 — M-LONG vs V-SHORT OOS Sortino by pair\n"
                 "(axes clipped to [-2, 8]; +3.0 = locked ship-floor)",
                 fontsize=11, pad=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    f17 = OUTDIR_FIG / "17_mlong_vs_vshort_matrix.png"
    plt.savefig(f17, dpi=140, bbox_inches="tight"); plt.close()
    print(f"Wrote {f17}")

    dump = {"seed": BOOT_SEED, "is_fraction": IS_FRACTION,
            "scheme_d_vshort": SCHEME_D, "faithfulness": {"dxy_mean_r": dxy_mr,
            "anchor": H8_ANCHOR, "pass": ok}, "skipped": skipped,
            "pairs": {s: {k: v for k, v in r.items() if k != "_v_equity"}
                      for s, r in results.items()}}
    jp = REPO / "results" / "_h25_run.json"
    jp.write_text(json.dumps(dump, indent=2, default=str))
    print(f"Wrote {jp}")
    n_go = sum(1 for r in results.values() if r["vshort_decision"] == "GO")
    print(f"\nV-SHORT GO count: {n_go} "
          f"({'wire hurst-agent integration' if n_go else 'NEGATIVE RESULT — no integration, document only'})")
    print("DONE.")


if __name__ == "__main__":
    main()
