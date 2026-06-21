#!/usr/bin/env python3
"""H30 Part 2 — Visual confirmation of detected boxes on DXY daily.

Uses the existing `box_pattern.detect_boxes_df` exactly as-is. Picks the
5 most-recent confirmed boxes (any direction, any bias verdict) and
renders them as a 5-panel composite (fig 26), then a single-image
full-history overview marking every detected box on the DXY timeline
(fig 27).
"""
from __future__ import annotations

import pathlib
import sys
from typing import Literal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import box_pattern as bp
from rsi_pattern import data as dm

OUTDIR = REPO / "figures"
OUTDIR.mkdir(exist_ok=True)


def load_dxy_daily() -> pd.DataFrame:
    dm.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return dm.load_dxy("daily")


def all_boxes(df: pd.DataFrame) -> list[bp.BoxPattern]:
    """H30c: chain_mode=True so boxes carry chain metadata and natural
    direction transitions (continuation + reversal)."""
    return bp.detect_boxes_df(df, chain_mode=True)


# H30c chain colour families — a base color per LONG/SHORT chain, darkened
# by chain_index (continuation boxes get progressively darker), and a
# distinct REVERSAL palette for the first box of each chain when it
# reverses a prior chain.
_LONG_BASE = ["#a1d99b", "#74c476", "#41ab5d", "#238b45", "#005a32"]
_SHORT_BASE = ["#fcae91", "#fb6a4a", "#de2d26", "#a50f15", "#67000d"]
_REVERSAL_LONG = "#1f78b4"
_REVERSAL_SHORT = "#6a3d9a"


def _chain_color(b: bp.BoxPattern) -> str:
    if b.reverses_chain_id is not None:
        return _REVERSAL_LONG if b.direction == "long" else _REVERSAL_SHORT
    base = _LONG_BASE if b.direction == "long" else _SHORT_BASE
    idx = min(b.chain_index or 0, len(base) - 1)
    return base[idx]


def _bias_color(b: bp.BoxPattern) -> str:
    if b.trade_aligned:
        return "#2ca02c" if b.direction == "long" else "#d62728"
    return "#888888"


def _height_pips(b: bp.BoxPattern) -> float:
    return abs(b.p1_price - b.p0_price) * 100.0   # DXY index points*100 ~ "pips-ish"


def _annotate_box(ax, df: pd.DataFrame, b: bp.BoxPattern, panel_n: int, total_n: int) -> None:
    pre = 40; post = 20
    a = max(b.p0_idx - pre, 0)
    z = min(b.p3_idx + post, len(df) - 1)
    sub = df.iloc[a:z + 1]
    ax.plot(sub.index, sub["close"], color="#222", linewidth=1.0)

    # Shade box: time = (P0 → P3), price = (P0_price → P1_price)
    box_t0 = df.index[b.p0_idx]
    box_t1 = df.index[b.p3_idx]
    lo = min(b.p0_price, b.p1_price); hi = max(b.p0_price, b.p1_price)
    rect = Rectangle(
        (matplotlib.dates.date2num(box_t0), lo),
        matplotlib.dates.date2num(box_t1) - matplotlib.dates.date2num(box_t0),
        hi - lo, facecolor=_chain_color(b), edgecolor="none", alpha=0.35,
        zorder=1,
    )
    ax.add_patch(rect)

    pts = [
        (b.p0_idx, b.p0_price, "P0", "#2ca02c"),
        (b.p1_idx, b.p1_price, "P1", "#d62728"),
        (b.p2_idx, b.p2_price, "P2", "#ff7f0e"),
        (b.p3_idx, b.p3_price, "P3", "#1f77b4"),
    ]
    for idx, price, lbl, c in pts:
        ax.scatter(df.index[idx], price, s=85, color=c,
                   edgecolor="black", linewidth=0.7, zorder=5)
        ax.annotate(lbl, (df.index[idx], price),
                    textcoords="offset points", xytext=(6, 7),
                    fontsize=9, fontweight="bold", color=c)

    # T-mid as vertical line
    mid_idx = int(b.t_mid)
    if 0 <= mid_idx < len(df):
        ax.axvline(df.index[mid_idx], color="#666",
                   linestyle=":", linewidth=1.2)
        ax.text(df.index[mid_idx], hi + 0.03 * (hi - lo),
                "T-mid", color="#666", fontsize=8, ha="center")

    side = "RIGHT of T-mid" if b.p1_idx > b.t_mid else \
           "LEFT of T-mid" if b.p1_idx < b.t_mid else "AT T-mid"
    aligned = "✓ aligned (trade)" if b.trade_aligned else "× countertrend (skip)"
    height_pips = _height_pips(b)
    bar_t0 = df.index[b.p0_idx].date(); bar_t1 = df.index[b.p3_idx].date()

    chain_tag = ""
    if b.chain_id is not None:
        chain_tag = (f"  ·  chain {b.chain_id}, index {b.chain_index}"
                     + (f", REVERSES chain {b.reverses_chain_id}"
                        if b.reverses_chain_id is not None else ""))
    title = (f"Box {panel_n}/{total_n} — {b.direction.upper()}  "
             f"{bar_t0} → {bar_t1}  ({b.length} bars){chain_tag}\n"
             f"P1 is {side} → {b.asymmetry}  ·  {aligned}  ·  "
             f"height ≈ {height_pips:.0f} DXY×100")
    ax.set_title(title, fontsize=10, loc="left")
    ax.grid(True, alpha=0.25)


def fig26_recent_panels(df: pd.DataFrame, boxes: list[bp.BoxPattern]) -> pathlib.Path:
    recent = boxes[-5:]
    n = len(recent)
    fig, axes = plt.subplots(n, 1, figsize=(13, 3.6 * n), constrained_layout=True)
    if n == 1:
        axes = [axes]
    for k, b in enumerate(recent, start=1):
        _annotate_box(axes[k - 1], df, b, panel_n=k, total_n=n)
    # Summarise chain stats across the full series for the figure title
    chains: dict = {}
    for x in boxes:
        if x.chain_id is not None:
            chains.setdefault(x.chain_id, []).append(x)
    longest = max((len(v) for v in chains.values()), default=0)
    n_chains = len(chains)
    n_reversal = sum(1 for v in chains.values()
                      if v and v[0].reverses_chain_id is not None)
    fig.suptitle(
        f"DXY daily — 5 most-recent detected box patterns (chain_mode)\n"
        f"P0 swing · P1 = running extreme at 50% retrace · P2 = first 50% retrace bar · "
        f"P3 = break of P1 · T-mid = (P0+P2)/2\n"
        f"chains: {n_chains} total · longest = {longest} boxes · reversal-started = {n_reversal}",
        fontsize=11)
    path = OUTDIR / "26_box_examples_dxy.png"
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def fig27_full_history(df: pd.DataFrame, boxes: list[bp.BoxPattern]) -> pathlib.Path:
    fig, ax = plt.subplots(figsize=(15, 6.5))
    ax.plot(df.index, df["close"], color="#222", linewidth=0.55)

    n_long_bull = sum(1 for b in boxes if b.direction == "long" and b.trade_aligned)
    n_short_bear = sum(1 for b in boxes if b.direction == "short" and b.trade_aligned)
    n_neutral = sum(1 for b in boxes if not b.trade_aligned)
    n_reversal = sum(1 for b in boxes if b.reverses_chain_id is not None)

    for b in boxes:
        x = df.index[b.p3_idx]
        y = float(df["close"].iloc[b.p3_idx])
        if b.reverses_chain_id is not None:
            # Reversal markers (chain breaks)
            mk = "P" if b.direction == "long" else "X"
            ax.scatter(x, y, marker=mk, s=40, color=_chain_color(b),
                       edgecolor="black", linewidth=0.6, zorder=4, alpha=0.9)
        elif b.direction == "long" and b.trade_aligned:
            ax.scatter(x, y, marker="^", s=22, color="#2ca02c",
                       edgecolor="black", linewidth=0.25, zorder=3, alpha=0.85)
        elif b.direction == "short" and b.trade_aligned:
            ax.scatter(x, y, marker="v", s=22, color="#d62728",
                       edgecolor="black", linewidth=0.25, zorder=3, alpha=0.85)
        else:
            ax.scatter(x, y, marker="o", s=10, color="#888",
                       edgecolor="none", zorder=2, alpha=0.5)

    handles = [
        plt.Line2D([0], [0], marker="^", color="w",
                   markerfacecolor="#2ca02c", markeredgecolor="black", markersize=8,
                   label=f"LONG box, bullish translation (n={n_long_bull})"),
        plt.Line2D([0], [0], marker="v", color="w",
                   markerfacecolor="#d62728", markeredgecolor="black", markersize=8,
                   label=f"SHORT box, bearish translation (n={n_short_bear})"),
        plt.Line2D([0], [0], marker="o", color="w",
                   markerfacecolor="#888", markersize=7,
                   label=f"countertrend / skipped (n={n_neutral})"),
        plt.Line2D([0], [0], marker="P", color="w",
                   markerfacecolor=_REVERSAL_LONG, markeredgecolor="black", markersize=9,
                   label=f"REVERSAL → LONG"),
        plt.Line2D([0], [0], marker="X", color="w",
                   markerfacecolor=_REVERSAL_SHORT, markeredgecolor="black", markersize=9,
                   label=f"REVERSAL → SHORT  (total reversals = {n_reversal})"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=9, framealpha=0.95)
    ax.set_title("DXY daily — every detected box, marked at P3 confirmation bar\n"
                 "green ▲ = LONG bullish-translation · red ▼ = SHORT bearish-translation · "
                 "gray ● = countertrend (filter rejects)", fontsize=11, pad=10)
    ax.set_ylabel("DXY close"); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = OUTDIR / "27_box_history_dxy.png"
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    df = load_dxy_daily()
    boxes = all_boxes(df)
    print(f"DXY daily: {len(df)} bars, {len(boxes)} boxes total "
          f"({sum(1 for b in boxes if b.direction == 'long')} long, "
          f"{sum(1 for b in boxes if b.direction == 'short')} short)")
    f26 = fig26_recent_panels(df, boxes)
    print(f"Wrote {f26}")
    f27 = fig27_full_history(df, boxes)
    print(f"Wrote {f27}")
    print("\n5 most-recent boxes (the ones shown in fig 26):")
    for b in boxes[-5:]:
        t0 = df.index[b.p0_idx].date(); t3 = df.index[b.p3_idx].date()
        side = "right" if b.p1_idx > b.t_mid else "left" if b.p1_idx < b.t_mid else "at"
        print(f"  {b.direction.upper():5s} {t0} → {t3} | "
              f"{b.length:>3d} bars | P1 {side} of T-mid → {b.asymmetry:8s} | "
              f"aligned={b.trade_aligned}")


if __name__ == "__main__":
    main()
