#!/usr/bin/env python3
"""H31a — USDJPY box-strict regime: H24 robustness + visual proof.

USDJPY under H31 ``box_strict`` was the first cell in the entire box-pattern
arc to clear BOTH the +3.0 Sortino floor (+5.03 OOS) AND the 30-trade floor
(32 OOS trades). H31's inline H24 pass reported DOWNGRADE (1/4 conditions).
This script:

1. Reconstructs the OOS trade list with the exact H31 engine path.
2. Runs the locked H24 4-test gate with full numbers:
     [1] Bootstrap N=10000 seed=42; p5 of Sortino across resamples (≥+3.0?)
     [2] Rolling 50%-OOS-span × 4 windows; ≥3/4 with Sortino ≥+3.0?
     [3] Gini of trade contribution ≤0.7?
     [4] Per-trade drop-one min Sortino ≥+2.5?
3. Applies the locked decision matrix (4/4 → SOLID_GO, 2-3 → THIN_GO,
   0-1 → DOWNGRADE_SWEEP).
4. Builds fig 34 (4-panel H24 visualization).
5. Selects 6-10 representative trades spanning the outcome range and
   builds fig 35 — for each, a candlestick chart centered on the entry
   with the LAST 5 COMPLETED BOXES preceding the entry overlaid and
   color-coded by translation verdict (green = bullish-asymmetry,
   red = bearish-asymmetry, gray = neutral). Each panel is annotated
   with entry date / entry price / Scheme G multiplier / regime label /
   R-multiple / exit reason.

This is verification, not shipping. hurst-agent is untouched regardless
of verdict.
"""
from __future__ import annotations

import json
import pathlib
import sys
import warnings
from dataclasses import dataclass
from typing import Optional

import matplotlib
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import box_pattern as bp
from rsi_pattern import indicators, position_sizing
from rsi_pattern.patterns import PatternConfig
from rsi_pattern import risk_metrics as rm

OUTDIR_FIG = REPO / "figures"
OUTDIR_FIG.mkdir(exist_ok=True)
CACHE_DIR = REPO / "data" / "yfinance_cache"

# H31 locked parameters
WINDOW_N = 5
THRESHOLD = "strict"
SCHEME_D = (0.0, 1.0, 3.0)   # bullish / neutral / bearish
IS_FRACTION = 0.70
DIP = 50.0

# H24 locked thresholds
SHIP_FLOOR = 3.0
PER_TRADE_FLOOR = 2.5
GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42

SYM = "USDJPY"
TKR = "USDJPY=X"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_usdjpy() -> pd.DataFrame:
    cache_path = CACHE_DIR / "USDJPY_X_daily.csv"
    if not cache_path.exists():
        raise FileNotFoundError(f"yfinance cache missing: {cache_path}")
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


# ---------------------------------------------------------------------------
# Engine — match H31 box_strict path EXACTLY
# ---------------------------------------------------------------------------

@dataclass
class TradeRow:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    r_multiple: float
    multiplier: float
    regime_label: str            # 'bullish_regime'/'bearish_regime'/'neutral_regime'/'unknown'
    entry_idx: int
    exit_idx: int
    exit_reason: str             # 'stop' / 'target' / 'trail' / 'time' (best-effort)


def _exit_reason(t) -> str:
    """Best-effort reason classification using FibTrade exit fields."""
    reason = getattr(t, "exit_reason", None)
    if reason:
        return str(reason)
    return "exit"


def build_oos_trades(df: pd.DataFrame) -> tuple[
        list[TradeRow], pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Rebuild the H31 box_strict OOS trade list with full metadata."""
    is_end = int(len(df) * IS_FRACTION)
    df_oos = df.iloc[is_end:]

    # H31 engine path — slice-local box detection (OOS-only) so the
    # regime series doesn't leak across the 70/30 boundary.
    dr = indicators.add_rsi(df_oos, period=14)
    cfg = PatternConfig(m_inner_threshold=DIP)
    trades = position_sizing.fib_long_at_p1(dr, rsi_col="rsi14", cfg=cfg)
    boxes_oos = bp.detect_boxes_df(df_oos, chain_mode=True)
    regime = bp.box_regime_series(df_oos, boxes=boxes_oos,
                                    window_n=WINDOW_N, threshold=THRESHOLD)

    bull_m, neut_m, bear_m = SCHEME_D
    out: list[TradeRow] = []
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        entry_ts = dr.index[t.entry_idx]
        lbl = regime.loc[entry_ts] if entry_ts in regime.index else "unknown"
        if lbl == "bullish_regime":
            mult = bull_m
        elif lbl == "bearish_regime":
            mult = bear_m
        else:
            mult = neut_m
        if mult == 0:
            continue  # 0× = skip (H31 bullish_regime drops the trade)
        out.append(TradeRow(
            entry_date=pd.Timestamp(entry_ts),
            exit_date=pd.Timestamp(dr.index[t.exit_idx]),
            entry_price=float(getattr(t, "entry_price", df_oos["close"].iloc[t.entry_idx])),
            exit_price=float(getattr(t, "exit_price",  df_oos["close"].iloc[t.exit_idx])),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
            regime_label=str(lbl),
            entry_idx=int(t.entry_idx),
            exit_idx=int(t.exit_idx),
            exit_reason=_exit_reason(t),
        ))
    return out, df_oos, df_oos.index[0], df_oos.index[-1]


# ---------------------------------------------------------------------------
# H24 — 4 tests
# ---------------------------------------------------------------------------

def _to_records(rows: list[TradeRow]) -> list[rm.TradeRecord]:
    return [rm.TradeRecord(entry_date=r.entry_date, exit_date=r.exit_date,
                            r_multiple=r.r_multiple, multiplier=r.multiplier)
            for r in rows]


def _sortino(recs: list[rm.TradeRecord]) -> float:
    if len(recs) < 2:
        return float("nan")
    eq = rm.build_equity_curve(recs, initial_capital=1.0, risk_per_trade=0.01)
    return rm.sortino(eq)


def test_bootstrap(recs: list[rm.TradeRecord]) -> dict:
    rng = np.random.RandomState(BOOT_SEED)
    np.random.seed(BOOT_SEED)
    n = len(recs)
    decision_vals = np.empty(N_BOOT, dtype=float)
    finite: list[float] = []
    for b in range(N_BOOT):
        idx = rng.randint(0, n, size=n)
        s = _sortino([recs[i] for i in idx])
        if np.isfinite(s):
            decision_vals[b] = s
            finite.append(s)
        else:
            decision_vals[b] = 0.0
    return {
        "n_boot": N_BOOT,
        "seed": BOOT_SEED,
        "nan_rate": float(1.0 - len(finite) / N_BOOT),
        "p5_decision": float(np.percentile(decision_vals, 5)),
        "p50_decision": float(np.percentile(decision_vals, 50)),
        "p95_decision": float(np.percentile(decision_vals, 95)),
        "p5_finite": float(np.percentile(finite, 5)) if finite else None,
        "p50_finite": float(np.percentile(finite, 50)) if finite else None,
        "p95_finite": float(np.percentile(finite, 95)) if finite else None,
        "_distribution": decision_vals,
        "pass": float(np.percentile(decision_vals, 5)) >= SHIP_FLOOR,
    }


def test_rolling(recs: list[rm.TradeRecord], oos_start: pd.Timestamp,
                  oos_end: pd.Timestamp) -> dict:
    span = (oos_end - oos_start).days
    win = pd.Timedelta(days=int(span * 0.50))
    starts_frac = np.linspace(0.0, 0.5, 4)
    windows = []
    for f in starts_frac:
        ws = oos_start + pd.Timedelta(days=int(span * f))
        we = ws + win
        sub = [r for r in recs if ws <= r.entry_date <= we]
        s = _sortino(sub)
        windows.append({
            "start": ws.date().isoformat(),
            "end": we.date().isoformat(),
            "n_trades": len(sub),
            "sortino": None if np.isnan(s) else float(round(s, 3)),
        })
    n_pass = sum(1 for w in windows
                  if w["sortino"] is not None and w["sortino"] >= SHIP_FLOOR)
    return {
        "window_days": int(win.days),
        "windows": windows,
        "n_ge_floor": n_pass,
        "pass": n_pass >= 3,
    }


def _gini(values: np.ndarray) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x); s = x.sum()
    if n == 0 or s == 0:
        return float("nan")
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * x)) / (n * s) - (n + 1.0) / n)


def test_clustering(recs: list[rm.TradeRecord]) -> dict:
    contrib = np.array([r.r_multiple * r.multiplier for r in recs])
    g_contrib = _gini(contrib)
    pos = np.clip(contrib, 0, None)
    total_profit = float(pos.sum())
    g_profit = _gini(pos) if total_profit > 0 else float("nan")
    best_share = 0.0
    if total_profit > 0:
        ts_pos = pd.Series(pos, index=[r.exit_date for r in recs]).sort_index()
        for ts in ts_pos.index:
            w = ts_pos[(ts_pos.index >= ts) &
                        (ts_pos.index < ts + pd.Timedelta(days=30))].sum()
            best_share = max(best_share, float(w / total_profit))
    return {
        "contribution": contrib.tolist(),
        "gini_contribution": None if np.isnan(g_contrib) else float(round(g_contrib, 4)),
        "gini_profit_only":  None if np.isnan(g_profit)  else float(round(g_profit, 4)),
        "single_30d_window_profit_share": float(round(best_share, 4)),
        "pass": (not np.isnan(g_contrib)) and g_contrib <= GINI_MAX,
    }


def test_sensitivity(recs: list[rm.TradeRecord]) -> dict:
    out = []
    for i in range(len(recs)):
        rem = [r for j, r in enumerate(recs) if j != i]
        s = _sortino(rem)
        out.append((i, s))
    finite = [(i, s) for i, s in out if np.isfinite(s)]
    if finite:
        min_i, min_s = min(finite, key=lambda kv: kv[1])
    else:
        min_i, min_s = (out[0][0], float("nan"))
    dropped = recs[min_i]
    return {
        "min_sortino": None if np.isnan(min_s) else float(round(min_s, 3)),
        "min_drop_trade": {
            "entry": dropped.entry_date.date().isoformat(),
            "exit":  dropped.exit_date.date().isoformat(),
            "r_multiple": float(round(dropped.r_multiple, 4)),
            "multiplier": dropped.multiplier,
        },
        "per_trade": [
            {"dropped_entry": recs[i].entry_date.date().isoformat(),
             "sortino": None if not np.isfinite(s) else float(round(s, 3))}
            for i, s in out
        ],
        "pass": (not np.isnan(min_s)) and min_s >= PER_TRADE_FLOOR,
    }


def decide(boot: dict, roll: dict, clus: dict, sens: dict) -> tuple[str, dict]:
    conds = {
        "bootstrap_p5>=+3.0":  bool(boot["pass"]),
        ">=3/4 rolling>=+3.0": bool(roll["pass"]),
        "Gini<=0.7":           bool(clus["pass"]),
        "per_trade_min>=+2.5": bool(sens["pass"]),
    }
    n_hold = sum(conds.values())
    verdict = ("SOLID_GO" if n_hold == 4
                 else "THIN_GO" if n_hold in (2, 3)
                 else "DOWNGRADE_SWEEP")
    return verdict, {"conditions": conds, "n_hold": n_hold}


# ---------------------------------------------------------------------------
# Figure 34 — H24 4-panel robustness visualization
# ---------------------------------------------------------------------------

def fig34_h24(boot: dict, roll: dict, clus: dict, sens: dict,
               verdict: str, dmeta: dict, baseline_sortino: float,
               n_trades: int) -> pathlib.Path:
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    ax_b, ax_r = axes[0]
    ax_g, ax_s = axes[1]

    # 1. Bootstrap distribution
    dist = boot["_distribution"]
    ax_b.hist(dist, bins=60, color="#1f77b4", edgecolor="black", alpha=0.85)
    ax_b.axvline(SHIP_FLOOR, color="green", linestyle="--", linewidth=1.6,
                  label=f"Ship floor +{SHIP_FLOOR:.1f}")
    ax_b.axvline(boot["p5_decision"], color="red", linestyle="-", linewidth=1.8,
                  label=f"p5 = {boot['p5_decision']:+.2f}")
    ax_b.axvline(boot["p50_decision"], color="black", linestyle=":", linewidth=1.2,
                  label=f"p50 = {boot['p50_decision']:+.2f}")
    ax_b.axvline(baseline_sortino, color="orange", linestyle="-.", linewidth=1.4,
                  label=f"baseline = {baseline_sortino:+.2f}")
    ax_b.set_title(f"[1] Bootstrap (N={boot['n_boot']}, seed={boot['seed']}) — "
                    f"{'PASS' if boot['pass'] else 'FAIL'} "
                    f"(p5 {'≥' if boot['pass'] else '<'} +{SHIP_FLOOR:.1f})",
                    fontsize=10)
    ax_b.set_xlabel("Sortino across resamples"); ax_b.set_ylabel("count")
    ax_b.legend(loc="upper right", fontsize=8)
    ax_b.grid(True, axis="y", alpha=0.3)

    # 2. Rolling-window timeline
    win_centers = [pd.Timestamp(w["start"]) +
                    (pd.Timestamp(w["end"]) - pd.Timestamp(w["start"])) / 2
                    for w in roll["windows"]]
    win_sortinos = [w["sortino"] if w["sortino"] is not None else np.nan
                     for w in roll["windows"]]
    win_n = [w["n_trades"] for w in roll["windows"]]
    bar_colors = ["#2ca02c" if (s is not None and s >= SHIP_FLOOR)
                   else "#d62728" for s in win_sortinos]
    xs = np.arange(len(win_centers))
    ax_r.bar(xs, [s if not np.isnan(s) else 0 for s in win_sortinos],
              color=bar_colors, edgecolor="black", linewidth=0.5)
    ax_r.axhline(SHIP_FLOOR, color="green", linestyle="--", linewidth=1.4)
    ax_r.set_xticks(xs)
    ax_r.set_xticklabels([f"W{i+1}\n{c.date()}\n(n={n})"
                           for i, (c, n) in enumerate(zip(win_centers, win_n))],
                          fontsize=8)
    for i, s in enumerate(win_sortinos):
        ax_r.text(i, s if not np.isnan(s) else 0,
                   f"{s:+.2f}" if not np.isnan(s) else "nan",
                   ha="center", va="bottom" if (s is not None and s >= 0) else "top",
                   fontsize=9, fontweight="bold")
    ax_r.set_title(f"[2] Rolling 50%-OOS-span × 4 — "
                    f"{'PASS' if roll['pass'] else 'FAIL'} "
                    f"({roll['n_ge_floor']}/4 ≥ +{SHIP_FLOOR:.1f}; need ≥3)",
                    fontsize=10)
    ax_r.set_ylabel("Sortino"); ax_r.grid(True, axis="y", alpha=0.3)

    # 3. Gini — sorted trade contributions
    contrib_sorted = np.sort(np.asarray(clus["contribution"]))
    ax_g.bar(np.arange(len(contrib_sorted)), contrib_sorted,
              color=["#2ca02c" if c >= 0 else "#d62728" for c in contrib_sorted],
              edgecolor="black", linewidth=0.4)
    ax_g.axhline(0, color="black", linewidth=0.5)
    gtxt = (f"Gini = {clus['gini_contribution']:.3f}"
             if clus['gini_contribution'] is not None else "Gini = nan")
    ax_g.set_title(f"[3] Trade contribution Gini — "
                    f"{'PASS' if clus['pass'] else 'FAIL'} "
                    f"({gtxt}; need ≤{GINI_MAX:.1f}; "
                    f"single-30d-profit-share = "
                    f"{clus['single_30d_window_profit_share']*100:.0f}%)",
                    fontsize=10)
    ax_g.set_xlabel("trade rank (low → high contribution)")
    ax_g.set_ylabel("contribution (r × multiplier)")
    ax_g.grid(True, axis="y", alpha=0.3)

    # 4. Per-trade drop-one
    drop_vals = [p["sortino"] if p["sortino"] is not None else np.nan
                  for p in sens["per_trade"]]
    drop_dates = [pd.Timestamp(p["dropped_entry"]) for p in sens["per_trade"]]
    ax_s.plot(drop_dates, drop_vals, marker="o", linewidth=1.0, markersize=4,
                color="#1f77b4")
    ax_s.axhline(PER_TRADE_FLOOR, color="green", linestyle="--", linewidth=1.4,
                   label=f"per-trade floor +{PER_TRADE_FLOOR:.1f}")
    ax_s.axhline(baseline_sortino, color="orange", linestyle="-.", linewidth=1.0,
                   label=f"baseline {baseline_sortino:+.2f}")
    min_s = sens['min_sortino']
    ax_s.set_title(f"[4] Per-trade drop-one — "
                    f"{'PASS' if sens['pass'] else 'FAIL'} "
                    f"(min Sortino "
                    f"{'≥' if sens['pass'] else '<'} +{PER_TRADE_FLOOR:.1f}; "
                    f"min={min_s if min_s is not None else 'nan'}"
                    f" dropping {sens['min_drop_trade']['entry']} "
                    f"R={sens['min_drop_trade']['r_multiple']:+.2f})",
                    fontsize=10)
    ax_s.set_ylabel("Sortino after dropping that trade")
    ax_s.legend(loc="lower right", fontsize=9)
    ax_s.grid(True, alpha=0.3)

    fig.suptitle(
        f"FIG 34 — H24 robustness on USDJPY box-strict (H31, {n_trades} OOS trades)\n"
        f"baseline Sortino = {baseline_sortino:+.2f}  ·  "
        f"verdict: {verdict} ({dmeta['n_hold']}/4 conditions hold)",
        fontsize=12)
    path = OUTDIR_FIG / "34_usdjpy_h24_robustness.png"
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Trade selection — span winners / average / losers
# ---------------------------------------------------------------------------

def select_examples(rows: list[TradeRow], n_target: int = 8) -> list[TradeRow]:
    by_r = sorted(rows, key=lambda r: r.r_multiple, reverse=True)
    if len(by_r) <= n_target:
        return by_r
    # 3 biggest winners, 3 around the median (avg), 2 losers
    winners = by_r[:3]
    losers = by_r[-2:]
    mid = len(by_r) // 2
    avg = by_r[mid - 1:mid + 2]
    picked: list[TradeRow] = []
    seen_dates: set = set()
    for r in winners + avg + losers:
        key = (r.entry_date, r.exit_date)
        if key in seen_dates:
            continue
        seen_dates.add(key)
        picked.append(r)
        if len(picked) >= n_target:
            break
    picked.sort(key=lambda r: r.entry_date)
    return picked


# ---------------------------------------------------------------------------
# Figure 35 — candlestick + box overlays for each chosen example
# ---------------------------------------------------------------------------

def _asym_color(asym: str) -> str:
    return {"bullish": "#2ca02c", "bearish": "#d62728"}.get(asym, "#888888")


def _draw_candles(ax, sub: pd.DataFrame) -> None:
    """Lightweight OHLC candlesticks via Rectangle + Line2D — no mplfinance dep."""
    if len(sub) == 0:
        return
    x = mdates.date2num(sub.index.to_pydatetime())
    if len(x) >= 2:
        width = 0.6 * (x[1] - x[0])
    else:
        width = 0.6
    for xi, (_, row) in zip(x, sub.iterrows()):
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        up = c >= o
        body_color = "#2ca02c" if up else "#d62728"
        edge_color = "black"
        # wick
        ax.plot([xi, xi], [l, h], color=edge_color, linewidth=0.5, zorder=2)
        # body
        body_lo = min(o, c); body_hi = max(o, c)
        body_h = max(body_hi - body_lo, (h - l) * 0.01)
        ax.add_patch(Rectangle((xi - width / 2, body_lo), width, body_h,
                                facecolor=body_color, edgecolor=edge_color,
                                linewidth=0.4, zorder=3))


def fig35_examples(df: pd.DataFrame, df_oos: pd.DataFrame,
                    rows: list[TradeRow]) -> pathlib.Path:
    """Multi-panel candlestick examples with box overlays + regime annotations."""
    n = len(rows)
    cols = 2
    rows_n = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows_n, cols,
                               figsize=(13.5, 4.6 * rows_n),
                               constrained_layout=True)
    if rows_n == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    # Detect OOS-only boxes once for the regime overlay lookup
    boxes_oos = bp.detect_boxes_df(df_oos, chain_mode=True)
    boxes_sorted = sorted(boxes_oos, key=lambda b: b.p3_idx)

    for k, tr in enumerate(rows):
        ax = axes[k]
        # Window: ~200 bars centered on entry, but extend to exit if needed
        center = tr.entry_idx
        half = 100
        a = max(center - half, 0)
        z = min(max(tr.exit_idx + 10, center + half), len(df_oos) - 1)
        sub = df_oos.iloc[a:z + 1]
        _draw_candles(ax, sub)

        # Last 5 completed boxes whose P3 ≤ entry_idx
        prev_boxes = [b for b in boxes_sorted if b.p3_idx <= tr.entry_idx][-WINDOW_N:]
        for b in prev_boxes:
            if b.p0_idx < a:    # box starts before window — clip the rectangle to window
                bx0 = a
            else:
                bx0 = b.p0_idx
            box_t0 = df_oos.index[bx0]
            box_t1 = df_oos.index[min(b.p3_idx, z)]
            lo = min(b.p0_price, b.p1_price)
            hi = max(b.p0_price, b.p1_price)
            color = _asym_color(b.asymmetry)
            ax.add_patch(Rectangle(
                (mdates.date2num(box_t0), lo),
                mdates.date2num(box_t1) - mdates.date2num(box_t0),
                hi - lo,
                facecolor=color, edgecolor=color,
                linewidth=0.8, alpha=0.22, zorder=1,
            ))
            # mark P1
            if a <= b.p1_idx <= z:
                ax.scatter(df_oos.index[b.p1_idx], b.p1_price,
                            s=22, color=color, edgecolor="black",
                            linewidth=0.5, zorder=4)

        # Entry / exit markers
        ax.axvline(tr.entry_date, color="#1f77b4", linewidth=1.2,
                    alpha=0.85, label="entry")
        ax.axvline(tr.exit_date, color="#666", linewidth=1.0,
                    linestyle=":", alpha=0.75, label="exit")
        ax.scatter([tr.entry_date], [tr.entry_price], s=80,
                    color="#1f77b4", edgecolor="black", linewidth=0.8,
                    zorder=6, marker="^")
        ax.scatter([tr.exit_date], [tr.exit_price], s=80,
                    color="white", edgecolor="#1f77b4", linewidth=1.0,
                    zorder=6, marker="v")

        # Annotation
        r = tr.r_multiple
        win_tag = "✓" if r > 0 else "✗"
        title = (f"Trade {k+1}/{n} {win_tag}  "
                  f"entry {tr.entry_date.date()} @ {tr.entry_price:.3f}  →  "
                  f"exit {tr.exit_date.date()} @ {tr.exit_price:.3f}\n"
                  f"regime: {tr.regime_label}  ·  mult: {tr.multiplier:.0f}×  ·  "
                  f"R = {r:+.2f}  ·  exit: {tr.exit_reason}  ·  "
                  f"contrib = {r * tr.multiplier:+.2f}R")
        ax.set_title(title, fontsize=9.5, loc="left")
        ax.grid(True, alpha=0.25)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)

    # Hide unused subplots
    for k in range(n, len(axes)):
        axes[k].axis("off")

    # Legend (once, top of figure)
    legend_handles = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#2ca02c",
                markeredgecolor="#2ca02c", markersize=12, alpha=0.5,
                label="bullish-translation box (P1 right of T-mid)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#d62728",
                markeredgecolor="#d62728", markersize=12, alpha=0.5,
                label="bearish-translation box"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#888888",
                markeredgecolor="#888888", markersize=12, alpha=0.5,
                label="neutral-translation box"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#1f77b4",
                markeredgecolor="black", markersize=10, label="M-P1 LONG entry"),
        Line2D([0], [0], marker="v", color="w", markerfacecolor="white",
                markeredgecolor="#1f77b4", markersize=10, label="exit"),
    ]
    fig.legend(handles=legend_handles, loc="upper center", ncol=5,
                fontsize=9, bbox_to_anchor=(0.5, 1.01), frameon=False)
    fig.suptitle(
        f"FIG 35 — USDJPY box-strict regime: representative OOS M-P1 LONG entries\n"
        f"Each panel: candlesticks ± ~100 bars · last 5 completed boxes "
        f"(color = translation verdict) · regime label / multiplier / R / exit\n"
        f"Selection: 3 biggest winners + 3 around median + 2 losers (no cherry-pick)",
        fontsize=11, y=1.05,
    )
    path = OUTDIR_FIG / "35_usdjpy_box_translation_examples.png"
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("H31a — USDJPY box-strict regime: H24 robustness + visual proof")
    print("=" * 78)

    df = load_usdjpy()
    rows, df_oos, oos0, oos1 = build_oos_trades(df)
    n = len(rows)
    print(f"\nUSDJPY {df.index[0].date()} → {df.index[-1].date()}  "
          f"({len(df)} bars)")
    print(f"OOS window {oos0.date()} → {oos1.date()}  ({len(df_oos)} bars)")
    print(f"OOS box-strict trades: {n}")
    if n == 0:
        print("Aborting — no OOS trades reconstructed.")
        sys.exit(1)

    recs = _to_records(rows)
    baseline = _sortino(recs)
    print(f"baseline OOS Sortino = {baseline:+.3f}  "
          f"(H31 report: +5.03; difference if any reflects engine refactor / "
          f"trade-count alignment).\n")

    boot = test_bootstrap(recs)
    roll = test_rolling(recs, oos0, oos1)
    clus = test_clustering(recs)
    sens = test_sensitivity(recs)
    verdict, dmeta = decide(boot, roll, clus, sens)

    print("--- H24 4-test gate ---")
    print(f"[1] bootstrap N={boot['n_boot']} seed={boot['seed']}: "
          f"p5={boot['p5_decision']:+.3f}  p50={boot['p50_decision']:+.3f}  "
          f"p95={boot['p95_decision']:+.3f}  nan-rate={boot['nan_rate']:.1%} "
          f"finite-p5={boot['p5_finite']:+.3f}  "
          f"→ {'PASS' if boot['pass'] else 'FAIL'}")
    print(f"[2] rolling 50%×4 windows: "
          f"{[w['sortino'] for w in roll['windows']]}  "
          f"({roll['n_ge_floor']}/4 ≥ +{SHIP_FLOOR:.1f})  "
          f"→ {'PASS' if roll['pass'] else 'FAIL'}")
    print(f"[3] Gini contribution = {clus['gini_contribution']}  "
          f"Gini profit-only = {clus['gini_profit_only']}  "
          f"single-30d-share = {clus['single_30d_window_profit_share']*100:.0f}%  "
          f"→ {'PASS' if clus['pass'] else 'FAIL'}")
    print(f"[4] per-trade min Sortino = {sens['min_sortino']}  "
          f"(drop {sens['min_drop_trade']['entry']} "
          f"R={sens['min_drop_trade']['r_multiple']:+.2f})  "
          f"→ {'PASS' if sens['pass'] else 'FAIL'}")
    print(f"CONDITIONS HELD: {dmeta['n_hold']}/4  →  VERDICT: {verdict}")

    print("\nWriting figures...")
    f34 = fig34_h24(boot, roll, clus, sens, verdict, dmeta, baseline, n)
    print(f"  {f34}")

    examples = select_examples(rows, n_target=8)
    print(f"\nSelected {len(examples)} representative trades:")
    for i, r in enumerate(examples, start=1):
        print(f"  {i}. {r.entry_date.date()} → {r.exit_date.date()}  "
              f"R={r.r_multiple:+.3f}  mult={r.multiplier:.0f}×  "
              f"regime={r.regime_label}  exit={r.exit_reason}")
    f35 = fig35_examples(df, df_oos, examples)
    print(f"\n  {f35}")

    out = {
        "symbol": SYM,
        "scheme": "box_strict (H31)",
        "oos_window": [oos0.date().isoformat(), oos1.date().isoformat(),
                        len(df_oos)],
        "n_trades": n,
        "baseline_sortino": round(float(baseline), 4),
        "h24": {
            "bootstrap": {k: v for k, v in boot.items() if not k.startswith("_")},
            "rolling": roll,
            "clustering": clus,
            "sensitivity": {k: v for k, v in sens.items()},
            "conditions_hold": dmeta["n_hold"],
            "verdict": verdict,
        },
        "trades": [
            {"entry": r.entry_date.date().isoformat(),
             "exit":  r.exit_date.date().isoformat(),
             "entry_price": round(r.entry_price, 4),
             "exit_price":  round(r.exit_price, 4),
             "r_multiple":  round(r.r_multiple, 4),
             "multiplier":  r.multiplier,
             "regime_label": r.regime_label,
             "exit_reason": r.exit_reason}
            for r in rows
        ],
    }
    json_path = REPO / "results" / "_h31a_usdjpy_h24.json"
    json_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"  {json_path}\nDONE.")


if __name__ == "__main__":
    main()
