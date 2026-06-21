#!/usr/bin/env python3
"""H31 — Box-translation aggregation as a drop-in for FLD bias.

Pre-registered question: does aggregating the *translation verdict* across
the recent N box patterns capture longer-component pressure better than the
simplified FLD bias term currently feeding Scheme D's sizing?

Pre-registered pass criterion:
  PASS         : box-regime variant clears GO on ≥ 3 of 7 majors
                  (matches FLD-bias baseline: DXY, EURUSD, USDCAD, thin
                  GBPUSD per H23/H24)
  STRONG PASS  : box-regime ADDS pairs to the GO list FLD couldn't reach
  FAIL         : can't match baseline → document and kill the line

Same Scheme D thresholds:
  GO    : OOS Sortino ≥ +3.0 AND full-sample trades ≥ 30
  NO-GO : OOS Sortino < +1.0 OR  full-sample trades < 10
  SWEEP : anything in between
H24 robustness gate is applied to any GO cell before promotion.

Cell matrix per pair × 3 variants:
  - 'fld_baseline' — H23/H24 reference (FLD bias 10/20/40 → Scheme D)
  - 'box_strict'   — box_regime_series window_n=5, threshold='strict'
  - 'box_relaxed'  — box_regime_series window_n=5, threshold='relaxed'

Hard constraint (per the brief): box-regime thresholds are GLOBAL — same
'strict' and 'relaxed' rules across all pairs, no per-pair tuning.

Live DXY cron is untouched. hurst-agent integration is GATED on ≥3 GO
clearing H24, and is staged separately.
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

from rsi_pattern import box_pattern as bp
from rsi_pattern import fld, indicators, position_sizing
from rsi_pattern.patterns import PatternConfig
from rsi_pattern import risk_metrics as rm

OUTDIR_FIG = REPO / "figures"
OUTDIR_FIG.mkdir(exist_ok=True)
CACHE_DIR = REPO / "data" / "yfinance_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SEED = 4242

# Identical to H23: 0× bullish / 1× neutral / 3× bearish — contrarian
# sizing on the M-P1 LONG pullback strategy. We're only swapping the
# regime-source feeding this mapping.
SCHEME_D = (0.0, 1.0, 3.0)
IS_FRACTION = 0.70
WINDOW_N = 5
SHIP_FLOOR = 3.0
TRADE_FLOOR_FULL = 30
NO_GO_SORTINO = 1.0
NO_GO_TRADES = 10

# H24 robustness gate (locked from H24 spec)
H24_PER_TRADE_FLOOR = 2.5
H24_GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42

YF_TICKERS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
}

YF_END = "2026-05-19"   # pinned to match H23 cache for reproducibility


# ---------------------------------------------------------------------------
# Data loaders (yfinance cached + DXY BarChart) — verbatim from H23
# ---------------------------------------------------------------------------

def load_yfinance_cached(ticker: str, start: str = "1990-01-01",
                          end: str = YF_END) -> pd.DataFrame:
    cache_path = CACHE_DIR / f"{ticker.replace('=', '_').replace('^', '')}_daily.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
        return df
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import yfinance as yf
        raw = yf.download(ticker, start=start, end=end, progress=False,
                          auto_adjust=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance returned empty for {ticker!r}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    df = pd.DataFrame({
        "open":   pd.to_numeric(raw["Open"], errors="coerce"),
        "high":   pd.to_numeric(raw["High"], errors="coerce"),
        "low":    pd.to_numeric(raw["Low"], errors="coerce"),
        "close":  pd.to_numeric(raw["Close"], errors="coerce"),
        "volume": pd.to_numeric(raw.get("Volume", 0), errors="coerce"),
    })
    df.index = pd.to_datetime(raw.index, utc=True)
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_index()
    df.to_csv(cache_path)
    return df


def load_dxy_daily() -> pd.DataFrame:
    from rsi_pattern import data as data_mod
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy("daily")


# ---------------------------------------------------------------------------
# Engine — generic run_one parameterized on the regime-source series
# ---------------------------------------------------------------------------

# Regime-source mapping: FLD bias_label → {bullish/bearish/neutral/unknown};
# box-regime → {bullish_regime/bearish_regime/neutral_regime/unknown}. The
# downstream Scheme D multiplier picker collapses both into the same 3 tiers.
def _multiplier_for(label: str) -> float:
    bull_m, neut_m, bear_m = SCHEME_D
    if label in ("bullish", "bullish_regime"):
        return bull_m
    if label in ("bearish", "bearish_regime"):
        return bear_m
    return neut_m  # 'neutral', 'neutral_regime', 'unknown' all map to neutral


def run_one(df: pd.DataFrame, *, regime_series: pd.Series,
             dip: float, label: str) -> dict:
    """Generic counterpart of H23's run_one. ``regime_series`` is the per-bar
    label that drives Scheme D sizing — pass either the FLD bias_label series
    or the box_regime_series output. Engine path is otherwise identical.
    """
    df_rsi = indicators.add_rsi(df, period=14)
    cfg = PatternConfig(m_inner_threshold=dip)
    trades = position_sizing.fib_long_at_p1(df_rsi, rsi_col="rsi14", cfg=cfg)
    records: list[rm.TradeRecord] = []
    label_counts: dict[str, int] = {}
    universe = 0
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        universe += 1
        entry_ts = df_rsi.index[t.entry_idx]
        if entry_ts in regime_series.index:
            lbl = regime_series.loc[entry_ts]
        else:
            lbl = "unknown"
        label_counts[lbl] = label_counts.get(lbl, 0) + 1
        mult = _multiplier_for(lbl)
        if mult == 0:
            continue
        records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(entry_ts),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    equity = rm.build_equity_curve(records, initial_capital=1.0,
                                    risk_per_trade=0.01)
    return {
        "label": label,
        "trades": len(records),
        "universe": universe,
        "label_counts": label_counts,
        "mean_R_weighted": (float(np.mean([r.r_multiple * r.multiplier
                                            for r in records]))
                              if records else float("nan")),
        "total_R_per_year": rm.total_r_per_year(records),
        "sharpe": rm.sharpe(equity),
        "sortino": rm.sortino(equity),
        "max_dd": rm.max_drawdown(equity),
        "records": records,
    }


# ---------------------------------------------------------------------------
# Decision rule — identical to H23
# ---------------------------------------------------------------------------

def go_no_go(oos: dict, full: dict) -> tuple[str, str]:
    s = oos["sortino"]
    full_n = full["trades"]
    oos_n = oos["trades"]
    if np.isnan(s):
        return "NO-GO", f"OOS Sortino undefined (OOS trades={oos_n})"
    if s >= SHIP_FLOOR and full_n >= TRADE_FLOOR_FULL:
        return "GO", (f"OOS Sortino {s:+.2f} ≥ {SHIP_FLOOR:.1f} AND full "
                       f"trades {full_n} ≥ {TRADE_FLOOR_FULL}")
    if s < NO_GO_SORTINO or full_n < NO_GO_TRADES:
        return "NO-GO", (f"OOS Sortino {s:+.2f} < {NO_GO_SORTINO:.1f} OR "
                          f"full trades {full_n} < {NO_GO_TRADES}")
    return "SWEEP", f"OOS Sortino {s:+.2f} ∈ [{NO_GO_SORTINO:.1f},{SHIP_FLOOR:.1f})"


def split_70_30(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    is_end = int(len(df) * IS_FRACTION)
    return df.iloc[:is_end], df.iloc[is_end:]


# ---------------------------------------------------------------------------
# Regime-source builders (one call per pair, caches box detection results)
# ---------------------------------------------------------------------------

def fld_baseline_series(df: pd.DataFrame) -> pd.Series:
    return fld.fld_bias(df, cycles=(10, 20, 40))["bias_label"]


def box_regime_for_pair(df: pd.DataFrame, *,
                         threshold: bp.RegimeThreshold,
                         boxes: Optional[list[bp.BoxPattern]] = None
                         ) -> pd.Series:
    """Build the box-regime label series for one pair. ``boxes`` lets the
    caller pre-detect once and reuse across strict/relaxed variants."""
    return bp.box_regime_series(df, boxes=boxes,
                                  window_n=WINDOW_N, threshold=threshold,
                                  chain_mode=True)


# ---------------------------------------------------------------------------
# H24 inline (gating any GO cell)
# ---------------------------------------------------------------------------

def _sortino_of(recs: list[rm.TradeRecord]) -> float:
    if len(recs) < 2:
        return float("nan")
    eq = rm.build_equity_curve(recs, initial_capital=1.0, risk_per_trade=0.01)
    return rm.sortino(eq)


def _gini(values: np.ndarray) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    s = x.sum()
    if n == 0 or s == 0:
        return float("nan")
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * x)) / (n * s) - (n + 1.0) / n)


def h24_robustness(recs: list[rm.TradeRecord], oos_start: pd.Timestamp,
                    oos_end: pd.Timestamp) -> dict:
    """Locked H24 4-test gate. SOLID_GO = 4/4, THIN_GO = 2-3/4,
    DOWNGRADE_SWEEP = ≤1/4. Returns dict with verdict + per-test detail."""
    if len(recs) < 2:
        return {
            "verdict": "DOWNGRADE_SWEEP",
            "reason": "fewer than 2 OOS trades — robustness undefined",
        }
    # 1. Bootstrap (decision-percentile counts nan as 0)
    rng = np.random.RandomState(BOOT_SEED)
    n = len(recs)
    decision_vals = np.empty(N_BOOT, dtype=float)
    finite_vals: list[float] = []
    for b in range(N_BOOT):
        idx = rng.randint(0, n, size=n)
        s = _sortino_of([recs[i] for i in idx])
        if np.isfinite(s):
            decision_vals[b] = s
            finite_vals.append(s)
        else:
            decision_vals[b] = 0.0
    boot_p5 = float(np.percentile(decision_vals, 5))
    # 2. Rolling-window
    span = (oos_end - oos_start).days
    win = pd.Timedelta(days=int(span * 0.50))
    windows = []
    for f in np.linspace(0.0, 0.5, 4):
        ws = oos_start + pd.Timedelta(days=int(span * f))
        we = ws + win
        sub = [r for r in recs if ws <= r.entry_date <= we]
        s = _sortino_of(sub)
        windows.append({
            "start": ws.date().isoformat(),
            "end": we.date().isoformat(),
            "n_trades": len(sub),
            "sortino": None if np.isnan(s) else round(float(s), 3),
        })
    n_pass = sum(1 for w in windows
                  if w["sortino"] is not None and w["sortino"] >= SHIP_FLOOR)
    # 3. Gini of per-trade contributions
    contrib = np.array([r.r_multiple * r.multiplier for r in recs])
    g_contrib = _gini(contrib)
    # 4. Per-trade sensitivity
    sens_vals: list[float] = []
    for i in range(len(recs)):
        rem = [r for j, r in enumerate(recs) if j != i]
        s = _sortino_of(rem)
        if np.isfinite(s):
            sens_vals.append(float(s))
    min_sens = float(min(sens_vals)) if sens_vals else float("nan")
    # Decision precedence
    c1 = boot_p5 >= SHIP_FLOOR
    c2 = n_pass >= 3
    c3 = (not np.isnan(g_contrib)) and g_contrib <= H24_GINI_MAX
    c4 = (not np.isnan(min_sens)) and min_sens >= H24_PER_TRADE_FLOOR
    conds = {
        "bootstrap_p5>=+3.0": bool(c1),
        ">=3/4 rolling>=+3.0": bool(c2),
        "Gini<=0.7": bool(c3),
        "per_trade_min>=+2.5": bool(c4),
    }
    n_hold = int(sum(conds.values()))
    verdict = ("SOLID_GO" if n_hold == 4 else
                 "THIN_GO" if n_hold in (2, 3) else "DOWNGRADE_SWEEP")
    return {
        "verdict": verdict,
        "n_hold": n_hold,
        "conditions": conds,
        "bootstrap": {
            "p5_decision": round(boot_p5, 3),
            "n_boot": N_BOOT,
            "finite_p5": (round(float(np.percentile(finite_vals, 5)), 3)
                            if finite_vals else None),
        },
        "rolling": {"windows": windows, "n_ge_floor": int(n_pass)},
        "gini_contribution": None if np.isnan(g_contrib) else round(g_contrib, 4),
        "per_trade_min_sortino": (None if np.isnan(min_sens)
                                     else round(min_sens, 3)),
    }


# ---------------------------------------------------------------------------
# Per-pair orchestration: 3 variants × {is, oos, full}
# ---------------------------------------------------------------------------

def evaluate_pair(sym: str, df: pd.DataFrame) -> dict:
    np.random.seed(SEED)
    # Detect boxes ONCE (chain_mode=True) and reuse across the strict /
    # relaxed splits. Box detection is over the full series — but
    # box_regime_series is causally safe (it only counts boxes with
    # p3_idx ≤ asof_idx), and we further restrict by passing only IS or
    # OOS slices through fld.fld_bias parity.
    boxes_full = bp.detect_boxes_df(df, chain_mode=True)

    df_is, df_oos = split_70_30(df)

    def build_series(d: pd.DataFrame, kind: str) -> pd.Series:
        if kind == "fld":
            return fld_baseline_series(d)
        # For box_strict/box_relaxed restrict box detection to ``d``'s
        # window so OOS labels don't see boxes from the IS half (causality).
        boxes_slice = bp.detect_boxes_df(d, chain_mode=True)
        thr = "strict" if kind == "box_strict" else "relaxed"
        return box_regime_for_pair(d, threshold=thr, boxes=boxes_slice)

    out: dict = {
        "symbol": sym,
        "data_first": df.index[0].date().isoformat(),
        "data_last": df.index[-1].date().isoformat(),
        "data_bars": len(df),
        "is_window": [df_is.index[0].date().isoformat(),
                       df_is.index[-1].date().isoformat(), len(df_is)],
        "oos_window": [df_oos.index[0].date().isoformat(),
                        df_oos.index[-1].date().isoformat(), len(df_oos)],
        "n_boxes_full": len(boxes_full),
        "variants": {},
    }

    for kind in ("fld", "box_strict", "box_relaxed"):
        full = run_one(df, regime_series=build_series(df, kind),
                        dip=50.0, label=f"{sym} {kind} FULL")
        is_m = run_one(df_is, regime_series=build_series(df_is, kind),
                        dip=50.0, label=f"{sym} {kind} IS")
        oos = run_one(df_oos, regime_series=build_series(df_oos, kind),
                        dip=50.0, label=f"{sym} {kind} OOS")
        decision, reason = go_no_go(oos, full)
        h24 = None
        if decision == "GO":
            h24 = h24_robustness(
                oos["records"],
                pd.Timestamp(df_oos.index[0]),
                pd.Timestamp(df_oos.index[-1]),
            )
        out["variants"][kind] = {
            "full": _strip_records(full),
            "is": _strip_records(is_m),
            "oos": _strip_records(oos),
            "decision": decision,
            "decision_reason": reason,
            "h24_robustness": h24,
        }
    return out


def _strip_records(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "records"}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig32_sortino_bars(results: dict[str, dict]) -> pathlib.Path:
    """Per-pair grouped bar chart of OOS Sortino across the 3 variants."""
    syms = list(results.keys())
    fld_vals = [results[s]["variants"]["fld"]["oos"]["sortino"] for s in syms]
    str_vals = [results[s]["variants"]["box_strict"]["oos"]["sortino"] for s in syms]
    rel_vals = [results[s]["variants"]["box_relaxed"]["oos"]["sortino"] for s in syms]

    def clean(arr):
        return [0.0 if np.isnan(v) else v for v in arr]
    fld_vals = clean(fld_vals); str_vals = clean(str_vals); rel_vals = clean(rel_vals)

    x = np.arange(len(syms))
    w = 0.27
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.bar(x - w, fld_vals, w, label="FLD baseline", color="#1f77b4",
            edgecolor="black", linewidth=0.5)
    ax.bar(x,       str_vals, w, label="Box-regime strict (5/5)",
            color="#2ca02c", edgecolor="black", linewidth=0.5)
    ax.bar(x + w, rel_vals, w, label="Box-regime relaxed (≥4/5)",
            color="#ff7f0e", edgecolor="black", linewidth=0.5)
    ax.axhline(SHIP_FLOOR, color="green", linestyle="--", linewidth=1.4,
                label=f"GO ship-floor (Sortino = +{SHIP_FLOOR:.1f})")
    ax.axhline(NO_GO_SORTINO, color="red", linestyle=":", linewidth=1.2,
                label=f"NO-GO floor (Sortino = +{NO_GO_SORTINO:.1f})")
    ax.set_xticks(x); ax.set_xticklabels(syms)
    ax.set_ylabel("OOS Sortino (annualized)")
    ax.set_title("H31 — OOS Sortino: FLD bias baseline vs box-translation regime "
                  "(strict 5/5, relaxed ≥4/5)\n"
                  "Drop-in substitution of the Scheme D regime-source feeding "
                  "the M-P1 LONG strategy", fontsize=11, pad=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.95)
    plt.tight_layout()
    path = OUTDIR_FIG / "32_box_regime_vs_fld_sortinos.png"
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def fig33_dxy_label_timeline(df_dxy: pd.DataFrame, results: dict) -> pathlib.Path:
    """DXY: close + FLD label vs box-regime strict vs relaxed, with M-P1
    entry bars overlaid (vertical ticks at the entry index)."""
    fld_ser = fld_baseline_series(df_dxy)
    boxes_dxy = bp.detect_boxes_df(df_dxy, chain_mode=True)
    str_ser = bp.box_regime_series(df_dxy, boxes=boxes_dxy,
                                     window_n=WINDOW_N, threshold="strict")
    rel_ser = bp.box_regime_series(df_dxy, boxes=boxes_dxy,
                                     window_n=WINDOW_N, threshold="relaxed")

    def to_numeric(s: pd.Series) -> pd.Series:
        m = {"bullish": +1, "bullish_regime": +1, "bearish": -1,
              "bearish_regime": -1, "neutral": 0, "neutral_regime": 0,
              "unknown": 0}
        return s.map(m).fillna(0).astype(int)

    fig, axes = plt.subplots(4, 1, figsize=(13, 11), sharex=True,
                               gridspec_kw={"height_ratios": [3, 1, 1, 1]})
    ax_price, ax_fld, ax_str, ax_rel = axes

    ax_price.plot(df_dxy.index, df_dxy["close"], color="#222", linewidth=0.7)
    ax_price.set_ylabel("DXY close"); ax_price.grid(True, alpha=0.3)
    ax_price.set_title("H31 — DXY label timelines: FLD bias vs box-regime "
                        "(strict / relaxed)\n"
                        "+1 = bullish · 0 = neutral/unknown · -1 = bearish",
                        fontsize=11)

    for ax, ser, ttl in (
        (ax_fld, to_numeric(fld_ser), "FLD bias (10,20,40)"),
        (ax_str, to_numeric(str_ser), "Box-regime strict (5/5)"),
        (ax_rel, to_numeric(rel_ser), "Box-regime relaxed (≥4/5)"),
    ):
        ax.fill_between(ser.index, 0, ser.values,
                          where=(ser.values > 0), step="post",
                          color="#2ca02c", alpha=0.6, label="bullish")
        ax.fill_between(ser.index, 0, ser.values,
                          where=(ser.values < 0), step="post",
                          color="#d62728", alpha=0.6, label="bearish")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_yticks([-1, 0, 1])
        ax.set_ylim(-1.4, 1.4)
        ax.set_ylabel(ttl, fontsize=9)
        ax.grid(True, alpha=0.25)

    # Overlay M-P1 LONG entry bars on the price axis (small ticks at the
    # bottom of the price panel)
    df_rsi = indicators.add_rsi(df_dxy, period=14)
    trades = position_sizing.fib_long_at_p1(
        df_rsi, rsi_col="rsi14",
        cfg=PatternConfig(m_inner_threshold=50.0))
    entries = [df_rsi.index[t.entry_idx] for t in trades
                if t.exit_idx is not None and t.r_multiple is not None]
    if entries:
        ymin, ymax = ax_price.get_ylim()
        ax_price.vlines(entries, ymin, ymin + 0.04 * (ymax - ymin),
                          color="#1f77b4", linewidth=0.6, alpha=0.8,
                          label=f"M-P1 entries (n={len(entries)})")
        ax_price.legend(loc="upper left", fontsize=9)

    plt.tight_layout()
    path = OUTDIR_FIG / "33_box_regime_label_timeline.png"
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("H31 — Box-translation regime classifier (drop-in for FLD bias)")
    print("=" * 78)

    data: dict[str, pd.DataFrame] = {}
    skipped: dict[str, str] = {}
    try:
        data["DXY"] = load_dxy_daily()
    except Exception as e:
        skipped["DXY"] = f"DXY load failed: {e}"
    for sym, tkr in YF_TICKERS.items():
        try:
            data[sym] = load_yfinance_cached(tkr)
        except Exception as e:
            skipped[sym] = f"{tkr}: {e}"

    print("\nPHASE 1 — Data inventory")
    for sym, df in data.items():
        print(f"  {sym:7s} | {len(df):>5d} bars | "
              f"{df.index[0].date()} → {df.index[-1].date()}")
    for sym, why in skipped.items():
        print(f"  {sym:7s} | SKIPPED — {why}")

    print("\nPHASE 2 — Per-symbol evaluation (3 variants × IS/OOS/FULL)")
    results: dict[str, dict] = {}
    for sym, df in data.items():
        r = evaluate_pair(sym, df)
        results[sym] = r
        print(f"\n--- {sym} --- ({r['data_first']} → {r['data_last']}, "
              f"{r['data_bars']} bars, boxes={r['n_boxes_full']})")
        print(f"  OOS window {r['oos_window'][0]} → {r['oos_window'][1]} "
              f"({r['oos_window'][2]} bars)")
        for kind, v in r["variants"].items():
            oos = v["oos"]; full = v["full"]
            h24 = v.get("h24_robustness")
            tag = (f"  [{kind:11s}] OOS S={oos['sortino']:+.2f} tr={oos['trades']:>3} "
                    f"univ={oos['universe']:>3} | FULL tr={full['trades']:>3} "
                    f"S={full['sortino']:+.2f} | {v['decision']}")
            if h24 is not None:
                tag += f" → H24 {h24['verdict']} ({h24['n_hold']}/4)"
            print(tag)

    print("\n" + "=" * 78)
    print("PHASE 3 — Pre-registered pass-criterion verdict")
    print("=" * 78)

    def n_go(kind: str) -> int:
        return sum(1 for r in results.values()
                    if r["variants"][kind]["decision"] == "GO")

    n_go_fld = n_go("fld")
    n_go_str = n_go("box_strict")
    n_go_rel = n_go("box_relaxed")
    print(f"  FLD baseline GOs : {n_go_fld}")
    print(f"  Box strict GOs   : {n_go_str}")
    print(f"  Box relaxed GOs  : {n_go_rel}")
    box_best = max(n_go_str, n_go_rel)
    fld_set = {s for s, r in results.items()
                if r["variants"]["fld"]["decision"] == "GO"}
    str_set = {s for s, r in results.items()
                if r["variants"]["box_strict"]["decision"] == "GO"}
    rel_set = {s for s, r in results.items()
                if r["variants"]["box_relaxed"]["decision"] == "GO"}
    added_pairs_any = (str_set - fld_set) | (rel_set - fld_set)
    if box_best < 3:
        verdict_overall = "FAIL"
    elif box_best > n_go_fld:
        verdict_overall = "STRONG_PASS"
    elif box_best == n_go_fld and added_pairs_any:
        verdict_overall = "STRONG_PASS"
    elif box_best == n_go_fld:
        verdict_overall = "PASS"
    else:  # ≥3 but < FLD count
        verdict_overall = ("PASS_WITH_MIGRATION" if added_pairs_any
                            else "PASS_BELOW_BASELINE")
    print(f"  ⇒ Overall verdict: {verdict_overall}")

    # GO migration summary
    print(f"  FLD GO pairs    : {sorted(fld_set)}")
    print(f"  Strict GO pairs : {sorted(str_set)}")
    print(f"  Relaxed GO pairs: {sorted(rel_set)}")
    added_str = sorted(str_set - fld_set)
    added_rel = sorted(rel_set - fld_set)
    lost_str = sorted(fld_set - str_set)
    lost_rel = sorted(fld_set - rel_set)
    if added_str:  print(f"  Strict added vs FLD : {added_str}")
    if added_rel:  print(f"  Relaxed added vs FLD: {added_rel}")
    if lost_str:   print(f"  Strict lost vs FLD  : {lost_str}")
    if lost_rel:   print(f"  Relaxed lost vs FLD : {lost_rel}")

    print("\nPHASE 4 — Comparison table (OOS Sortino / OOS trades / decision)")
    hdr = (f"{'Sym':<8}{'FLD baseline':>20}{'Box strict (5/5)':>22}"
            f"{'Box relaxed (≥4/5)':>23}")
    print(hdr); print("-" * len(hdr))
    for sym, r in results.items():
        fld_v = r["variants"]["fld"]
        str_v = r["variants"]["box_strict"]
        rel_v = r["variants"]["box_relaxed"]
        def cell(v):
            s = v["oos"]["sortino"]
            return (f"{('nan' if np.isnan(s) else f'{s:+.2f}'):>6}/"
                     f"{v['oos']['trades']:>2} {v['decision']:<6}")
        print(f"{sym:<8}{cell(fld_v):>20}{cell(str_v):>22}{cell(rel_v):>23}")

    print("\nPHASE 5 — Figures")
    f32 = fig32_sortino_bars(results)
    print(f"  Wrote {f32}")
    if "DXY" in data:
        f33 = fig33_dxy_label_timeline(data["DXY"], results["DXY"])
        print(f"  Wrote {f33}")

    serializable = {
        "seed": SEED,
        "is_fraction": IS_FRACTION,
        "scheme_d": SCHEME_D,
        "window_n": WINDOW_N,
        "yf_end": YF_END,
        "overall_verdict": verdict_overall,
        "go_counts": {"fld": n_go_fld, "box_strict": n_go_str, "box_relaxed": n_go_rel},
        "go_sets": {"fld": sorted(fld_set), "box_strict": sorted(str_set),
                     "box_relaxed": sorted(rel_set)},
        "symbols": {sym: r for sym, r in results.items()},
        "skipped": skipped,
    }
    json_path = REPO / "results" / "_h31_run.json"
    json_path.write_text(json.dumps(serializable, indent=2, default=str))
    print(f"  Wrote {json_path}")
    print("\nDONE.")


if __name__ == "__main__":
    main()
