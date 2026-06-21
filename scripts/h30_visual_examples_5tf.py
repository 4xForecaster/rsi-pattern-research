#!/usr/bin/env python3
"""H30 follow-up — Visual examples of the corrected box pattern across
M5, M15, H1, H4, Daily for DXY. One per category × per timeframe:
  * bullish-aligned    → figures/28_box_bullish_examples_5tf.png
  * bearish-aligned    → figures/29_box_bearish_examples_5tf.png
  * failure (countertrend / gate skip) → figures/30_box_failure_examples_5tf.png

"Failure" per the spec autonomy rule: a detected box where direction and
translation DISAGREE (LONG box + bearish-translation OR SHORT box +
bullish-translation) — i.e. the H30 gate skipped it as countertrend.
Documented in each panel's annotation.

Uses ``box_pattern.detect_boxes_df`` as-is (corrected defaults
t_endpoint='p2', max_length=250). No detector modification, no tuning.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import box_pattern as bp
from rsi_pattern import data as dm

OUTDIR = REPO / "figures"
DOCS_COPY = pathlib.Path.home() / "Documents" / "4xForecaster"

# Variant A target levels (current H30 spec) — anchored on P2.
LEVELS = (1.618, 2.236)

TIMEFRAMES = ["M5", "M15", "H1", "H4", "Daily"]


# ---------------------------------------------------------------------------
# Data loaders / resampling
# ---------------------------------------------------------------------------

def load_dxy_native(tf: str) -> pd.DataFrame:
    """Load BarChart-native DXY for one of the documented timeframes."""
    dm.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return dm.load_dxy(tf)


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])
    return out


def load_dxy_5tf() -> dict[str, pd.DataFrame]:
    """Return {tf: DataFrame} for the five timeframes Dr. A specified.
    M15 is resampled from M5; H4 is the native BarChart 4h CSV."""
    out: dict[str, pd.DataFrame] = {}
    m5 = load_dxy_native("5m");   out["M5"] = m5
    out["M15"] = resample_ohlc(m5, "15min")
    out["H1"] = load_dxy_native("1h")
    out["H4"] = load_dxy_native("4h")
    out["Daily"] = load_dxy_native("daily")
    return out


# ---------------------------------------------------------------------------
# Box selection
# ---------------------------------------------------------------------------

MIN_LEN_BARS = 20
MAX_LEN_BARS = 100
MIN_DELTA_BARS = 3
MIN_HEIGHT_FRAC = 0.005   # 0.5% of median price — same floor as detection


def _height_frac(b: bp.BoxPattern, df: pd.DataFrame) -> float:
    return b.height / float(np.median(df["close"]))


def _delta_bars(b: bp.BoxPattern) -> float:
    return b.p1_idx - b.t_mid


def _clarity_score(b: bp.BoxPattern, df: pd.DataFrame) -> float:
    """Bigger = clearer. Combines: |P1 − T_mid| (further from midpoint =
    clearer translation read), height (taller box = clearer geometry),
    and a length sweet-spot factor that peaks at ~50-bar boxes."""
    delta = abs(_delta_bars(b))
    height = _height_frac(b, df)
    length = b.length
    length_score = 1.0 - abs(length - 50.0) / 50.0  # peaks at length≈50
    return float(delta) + 30.0 * height + 5.0 * max(0.0, length_score)


def pick_example(boxes: list[bp.BoxPattern], df: pd.DataFrame,
                 category: str) -> Optional[bp.BoxPattern]:
    """Pick the clearest example matching the category, respecting the
    spec's geometry constraints. If no box passes strict constraints, relax
    length to [10, 150] before giving up."""
    def pool(strict: bool) -> list[bp.BoxPattern]:
        candidates = []
        lo, hi = (MIN_LEN_BARS, MAX_LEN_BARS) if strict else (10, 150)
        for b in boxes:
            if not (lo <= b.length <= hi):
                continue
            if abs(_delta_bars(b)) < MIN_DELTA_BARS and category != "failure":
                continue
            if _height_frac(b, df) < MIN_HEIGHT_FRAC:
                continue
            if category == "bullish":
                if b.direction == "long" and b.asymmetry == "bullish" and b.trade_aligned:
                    candidates.append(b)
            elif category == "bearish":
                if b.direction == "short" and b.asymmetry == "bearish" and b.trade_aligned:
                    candidates.append(b)
            elif category == "failure":
                if b.asymmetry != "neutral" and not b.trade_aligned:
                    candidates.append(b)
        return candidates
    cands = pool(strict=True) or pool(strict=False)
    if not cands:
        return None
    return max(cands, key=lambda b: _clarity_score(b, df))


# ---------------------------------------------------------------------------
# Panel rendering
# ---------------------------------------------------------------------------

def _pip_value(df_close_median: float) -> float:
    """A rough 'pip' for labelling. DXY index → 1 pip ≈ 0.01. For most FX
    pairs that would be 0.0001; this script is DXY-only so 0.01 it is."""
    return 0.01


def _human_pips(height_price: float, df_close_median: float) -> str:
    pip = _pip_value(df_close_median)
    pips = height_price / pip
    return f"{pips:.0f} pip" if pips >= 1.0 else f"{height_price:.4f}"


def _frame(box: bp.BoxPattern, df: pd.DataFrame,
           pre_bars: int = 60, post_bars: int = 50
           ) -> tuple[int, int]:
    a = max(0, box.p0_idx - pre_bars)
    z = min(len(df) - 1, box.p3_idx + post_bars)
    # Widen if the framed window is < 150 bars (per spec target ~150-300)
    if z - a < 150:
        pad = (150 - (z - a)) // 2
        a = max(0, a - pad)
        z = min(len(df) - 1, z + pad)
    return a, z


def _variant_a_targets(box: bp.BoxPattern) -> tuple[float, float]:
    sign = +1.0 if box.direction == "long" else -1.0
    return (box.p2_price + sign * LEVELS[0] * box.height,
            box.p2_price + sign * LEVELS[1] * box.height)


def annotate_panel(ax, df: pd.DataFrame, box: Optional[bp.BoxPattern],
                    tf: str, panel_n: int, total_n: int, category: str,
                    absent_reason: Optional[str] = None) -> None:
    if box is None:
        ax.set_facecolor("#f5f5f5")
        ax.text(0.5, 0.5,
                f"{tf} · DXY\nNo clean {category} example available\non this timeframe\n\n{absent_reason or ''}",
                ha="center", va="center", fontsize=18, color="#666",
                transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{tf} · DXY · Box —/— (none)", fontsize=14, loc="left",
                     pad=6)
        return

    a, z = _frame(box, df)
    sub = df.iloc[a:z + 1]
    ax.plot(sub.index, sub["close"], color="#222", linewidth=1.2)

    # Box shading: x = (P0, P3), y = (min(P0,P1), max(P0,P1))
    x0 = mdates.date2num(df.index[box.p0_idx].to_pydatetime())
    x1 = mdates.date2num(df.index[box.p3_idx].to_pydatetime())
    lo, hi = sorted((box.p0_price, box.p1_price))
    ax.add_patch(Rectangle((x0, lo), x1 - x0, hi - lo,
                            facecolor="#dddddd", edgecolor="none",
                            alpha=0.40, zorder=1))

    # 4 points
    pts = [
        (box.p0_idx, box.p0_price, "P0", "#2ca02c",
         "swing low" if box.direction == "long" else "swing high"),
        (box.p1_idx, box.p1_price, "P1", "#d62728",
         "peak" if box.direction == "long" else "trough"),
        (box.p2_idx, box.p2_price, "P2", "#ff7f0e", "50% retrace"),
        (box.p3_idx, box.p3_price, "P3", "#1f77b4",
         "breakout" if box.direction == "long" else "breakdown"),
    ]
    for idx, price, lbl, c, role in pts:
        ax.scatter(df.index[idx], price, s=200, color=c,
                   edgecolor="black", linewidth=1.0, zorder=6)
        ax.annotate(f"{lbl}: {role}", (df.index[idx], price),
                    textcoords="offset points", xytext=(10, 12),
                    fontsize=13, fontweight="bold", color=c, zorder=7)

    # Height bracket on the LEFT edge of the panel
    x_left = df.index[a]
    h_lo, h_hi = sorted((box.p0_price, box.p1_price))
    ax.annotate("",
                xy=(x_left, h_lo), xytext=(x_left, h_hi),
                arrowprops=dict(arrowstyle="|-|", color="black", lw=1.4,
                                shrinkA=0, shrinkB=0))
    ax.text(x_left, (h_lo + h_hi) / 2,
             f"  height\n  {_human_pips(box.height, float(np.median(df['close'])))}\n  ({box.height:.4f})",
             ha="left", va="center", fontsize=11,
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="#999", alpha=0.85))

    # Variant A targets T1, T2 — anchored at P2, projected from end of P2 in breakout direction
    t1, t2 = _variant_a_targets(box)
    x_p2 = df.index[box.p2_idx]
    x_end = df.index[z]
    for level_label, level_price, level_mult in (("T1", t1, LEVELS[0]),
                                                  ("T2", t2, LEVELS[1])):
        ax.hlines(level_price, x_p2, x_end, linestyles="dashed",
                  colors="#444", linewidth=1.6, alpha=0.85, zorder=3)
        ax.text(x_end, level_price,
                 f"  {level_label} ({level_mult:.3f}×) · {level_price:.4f}",
                 ha="left", va="center", fontsize=12, color="#444",
                 fontweight="bold")

    # T1/2 vertical line at the corrected midpoint
    t_mid_idx = int(round(box.t_mid))
    if 0 <= t_mid_idx < len(df):
        ax.axvline(df.index[t_mid_idx], color="#1f77b4",
                   linestyle="dashed", linewidth=1.8, alpha=0.9)
        ax.text(df.index[t_mid_idx], h_hi + (h_hi - h_lo) * 0.05,
                 " T1/2\n (P0+P2)/2",
                 ha="left", va="bottom", fontsize=12, color="#1f77b4",
                 fontweight="bold")

    # Asymmetry annotation box
    delta = _delta_bars(box)
    side = "right" if delta > 0 else "left" if delta < 0 else "at"
    trade_taken = ("YES (aligned)" if box.trade_aligned
                   else "NO (countertrend skip)")
    direction_label = ("LONG box" if box.direction == "long"
                       else "SHORT box")
    chain_line = ""
    if box.chain_id is not None:
        chain_line = (f"\nChain: id={box.chain_id}, index={box.chain_index}"
                       + (f", REVERSES chain {box.reverses_chain_id}"
                          if box.reverses_chain_id is not None else ""))
    annotation = (f"Direction: {direction_label}\n"
                  f"Bars from T1/2 to P1: {delta:+.1f} bars  ({side} of T1/2)\n"
                  f"Verdict: {box.asymmetry}-translation\n"
                  f"Trade taken: {trade_taken}{chain_line}")
    ax.text(0.02, 0.97, annotation, transform=ax.transAxes,
             fontsize=12, va="top", ha="left",
             bbox=dict(boxstyle="round,pad=0.55", facecolor="#fff9d6",
                       edgecolor="#bb8800", linewidth=1.0))

    # Title
    title = (f"{tf} · DXY · Box {panel_n} of {total_n}  "
             f"({df.index[box.p0_idx].date()} → {df.index[box.p3_idx].date()})")
    ax.set_title(title, fontsize=15, loc="left", pad=10)
    ax.grid(True, alpha=0.30)


# ---------------------------------------------------------------------------
# Figure assembly
# ---------------------------------------------------------------------------

def make_figure(category: str, data: dict[str, pd.DataFrame],
                 out_path: pathlib.Path) -> dict[str, str]:
    """Render 5 stacked panels (M5, M15, H1, H4, Daily) for a category.
    Returns a dict {tf: status} where status is 'clean' or 'no example'."""
    fig, axes = plt.subplots(len(TIMEFRAMES), 1, figsize=(24, 30),
                              constrained_layout=True)
    status: dict[str, str] = {}
    for k, tf in enumerate(TIMEFRAMES):
        df = data[tf]
        # H30c: use chain_mode so direction transitions arise from real chain
        # continuation/reversal, and chain metadata is available for the
        # title annotations.
        all_boxes = bp.detect_boxes_df(df, chain_mode=True)
        chosen = pick_example(all_boxes, df, category)
        if chosen is None:
            status[tf] = "no example"
            annotate_panel(axes[k], df, None, tf, panel_n=k + 1,
                           total_n=len(TIMEFRAMES), category=category,
                           absent_reason=("Detector found "
                                          f"{len(all_boxes)} boxes total but "
                                          "none matched the category + "
                                          "geometry-clarity constraints "
                                          "(length 20–100 bars, |Δ|≥3 from T1/2, "
                                          "height ≥0.5% of price)."))
        else:
            status[tf] = "clean"
            annotate_panel(axes[k], df, chosen, tf, panel_n=k + 1,
                           total_n=len(TIMEFRAMES), category=category)
    title_text = {
        "bullish": "DXY · BULLISH-ALIGNED box examples across 5 timeframes\n"
                   "(LONG box + bullish translation + P3 confirms above P1; "
                   "Variant A targets T1=1.618×, T2=2.236× height from P2)",
        "bearish": "DXY · BEARISH-ALIGNED box examples across 5 timeframes\n"
                   "(SHORT box + bearish translation + P3 confirms below P1; "
                   "Variant A targets T1=1.618×, T2=2.236× height from P2)",
        "failure": "DXY · FAILURE (countertrend / gate skip) examples across 5 timeframes\n"
                   "Failure = direction & translation DISAGREE — what the H30 strict "
                   "confirmation gate rejects (LONG+bearish-translation OR SHORT+bullish-translation)",
    }[category]
    fig.suptitle(title_text, fontsize=18, fontweight="bold")
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return status


def main() -> None:
    OUTDIR.mkdir(exist_ok=True)
    DOCS_COPY.mkdir(exist_ok=True)
    data = load_dxy_5tf()
    print("Loaded DXY across 5 timeframes:")
    for tf in TIMEFRAMES:
        df = data[tf]
        print(f"  {tf:5s} {len(df):>6d} bars  {df.index[0]} → {df.index[-1]}")

    out_paths = {
        "bullish": OUTDIR / "28_box_bullish_examples_5tf.png",
        "bearish": OUTDIR / "29_box_bearish_examples_5tf.png",
        "failure": OUTDIR / "30_box_failure_examples_5tf.png",
    }
    report: dict[str, dict[str, str]] = {}
    for category, out in out_paths.items():
        print(f"\n=== Building {category} figure → {out.name}")
        status = make_figure(category, data, out)
        report[category] = status
        for tf, st in status.items():
            print(f"  {tf:5s} : {st}")
        # Copy to ~/Documents/4xForecaster/
        target = DOCS_COPY / out.name
        target.write_bytes(out.read_bytes())
        print(f"  copied to {target}")

    print("\nCategory × timeframe matrix:")
    print(f"  {'TF':5s} {'bullish':>10s} {'bearish':>10s} {'failure':>10s}")
    for tf in TIMEFRAMES:
        print(f"  {tf:5s} {report['bullish'][tf]:>10s} "
              f"{report['bearish'][tf]:>10s} {report['failure'][tf]:>10s}")
    print("\nDONE.")


if __name__ == "__main__":
    main()
