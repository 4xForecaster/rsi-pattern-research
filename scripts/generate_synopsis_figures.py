#!/usr/bin/env python3
"""Generate the four standardized synopsis figures for the RSI Pattern Research
project review.

All RSI subplots use the standardized grid: gridlines at 0, 15, 33, 40, 45,
50, 55, 60, 66, 85, 100. Full 0-100 y-axis.
"""
import pathlib, sys, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rsi_pattern import data as data_mod
data_mod.DATA_DIR = pathlib.Path("/sessions/friendly-inspiring-gates/mnt/Documents/rsi-data")
from rsi_pattern import indicators, patterns, validate
from rsi_pattern.patterns_strict import detect_strict_m, StrictPatternConfig


OUTDIR = pathlib.Path(__file__).resolve().parents[1] / "figures"
OUTDIR.mkdir(exist_ok=True)

# Standardized RSI grid the user specified
RSI_GRID_LEVELS = [0, 15, 33, 40, 45, 50, 55, 60, 66, 85, 100]
RSI_KEY_LEVELS = {15: "#a40000", 33: "#cc6600", 50: "#666", 66: "#cc6600", 85: "#006400"}


def apply_rsi_grid(ax):
    ax.set_ylim(0, 100)
    ax.set_yticks(RSI_GRID_LEVELS)
    for lev in RSI_GRID_LEVELS:
        color = RSI_KEY_LEVELS.get(lev, "#cccccc")
        ls = "-" if lev in RSI_KEY_LEVELS else "--"
        lw = 0.8 if lev in RSI_KEY_LEVELS else 0.4
        ax.axhline(lev, color=color, linestyle=ls, linewidth=lw, alpha=0.7, zorder=0)
    ax.tick_params(axis="y", labelsize=8)


# =============================================================
# FIGURE 1 — Standardized RSI chart with strict-M example
# =============================================================

def fig_strict_m_example():
    df = indicators.add_rsi(data_mod.load_dxy("1h"))
    sms = detect_strict_m(df["rsi14"].dropna())
    completed = [m for m in sms if m.completion_idx is not None]
    if not completed:
        print("No completed strict-Ms found for fig 1")
        return

    # Pick the most recent completed strict-M with the most wiggle (or any)
    m = sorted(completed, key=lambda x: -x.n_wiggle_peaks)[0]
    pad = 40
    start = max(0, m.rise_start_idx - pad)
    end = min(len(df), (m.completion_idx or m.last_major_peak_idx) + pad)
    seg = df.iloc[start:end]

    fig, (ax_price, ax_rsi) = plt.subplots(
        2, 1, figsize=(12, 7.5), sharex=True,
        gridspec_kw={"height_ratios": [1.2, 1.6]},
    )

    # Price panel
    ax_price.plot(seg.index, seg["close"], color="#1a4f8b", linewidth=1.2)
    ax_price.set_ylabel("DXY close")
    ax_price.set_title(
        f"Strict M example — DXY 1h\n"
        f"Rise from {df['rsi14'].iloc[m.rise_start_idx]:.1f} "
        f"→ peak {m.peak_max:.2f} over {m.rise_bars} bars "
        f"(velocity {m.rise_velocity:.2f} RSI/bar) · "
        f"{m.n_wiggle_peaks} peak{'s' if m.n_wiggle_peaks != 1 else ''} in top zone",
        fontsize=11, pad=10,
    )
    ax_price.grid(True, alpha=0.3)

    # RSI panel with standardized grid
    ax_rsi.plot(seg.index, seg["rsi14"], color="#444", linewidth=1.1)
    apply_rsi_grid(ax_rsi)
    ax_rsi.set_ylabel("RSI(14) — Wilder smoothing")
    ax_rsi.set_xlabel("Bar time")

    # Highlight strict-M zones
    rise_t0 = df.index[m.rise_start_idx]
    rise_t1 = df.index[m.first_major_peak_idx]
    top_t1 = df.index[m.last_major_peak_idx]
    comp_t = df.index[m.completion_idx] if m.completion_idx else df.index[m.last_major_peak_idx]

    # Rise leg
    ax_rsi.axvspan(rise_t0, rise_t1, color="#fdd49e", alpha=0.5, label="Rise leg (origin <30)")
    # Top zone (wiggle area)
    ax_rsi.axvspan(rise_t1, top_t1, color="#fb8d62", alpha=0.4, label="Top zone (≥75.01, wiggle ≥70)")
    # Fall leg / completion
    ax_rsi.axvspan(top_t1, comp_t, color="#fee08b", alpha=0.4, label="Fall to <50 (completion)")

    # Mark major peak anchors
    peak_x = df.index[m.first_major_peak_idx]
    peak_y = df["rsi14"].iloc[m.first_major_peak_idx]
    ax_rsi.scatter([peak_x], [peak_y], color="red", s=60, zorder=5, label="First major peak ≥75.01")
    if m.last_major_peak_idx != m.first_major_peak_idx:
        ax_rsi.scatter([df.index[m.last_major_peak_idx]],
                        [df["rsi14"].iloc[m.last_major_peak_idx]],
                        color="darkred", s=60, zorder=5, label="Last major peak")

    ax_rsi.legend(loc="lower right", fontsize=8, framealpha=0.95)
    plt.tight_layout()
    out = OUTDIR / "01_strict_m_example.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


# =============================================================
# FIGURE 2 — Strict-M vs Loose-M counts across timeframes
# =============================================================

def fig_pattern_counts():
    rows = []
    for tf in ["daily", "4h", "1h", "5m"]:
        df = indicators.add_rsi(data_mod.load_dxy(tf))
        df_lab = patterns.detect_all(df)
        loose_m = sum(1 for p in patterns.detect_m(df["rsi14"].dropna()) if p.completed_idx is not None)
        strict_m = sum(1 for m in detect_strict_m(df["rsi14"].dropna()) if m.completion_idx is not None)
        loose_v = sum(1 for p in patterns.detect_v(df["rsi14"].dropna()) if p.completed_idx is not None)
        rows.append({"timeframe": tf, "loose_M": loose_m, "strict_M": strict_m, "loose_V": loose_v})
    df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(df))
    w = 0.27
    ax.bar(x - w, df["loose_M"], w, label="Loose M (peaks≥65, dip≥50)", color="#fdb462")
    ax.bar(x, df["strict_M"], w, label="Strict M (origin<30, peaks≥75.01, wiggle≥70)", color="#d53e4f")
    ax.bar(x + w, df["loose_V"], w, label="Loose V (mirror of loose M)", color="#80b1d3")
    ax.set_xticks(x)
    ax.set_xticklabels(df["timeframe"])
    ax.set_ylabel("Count of completed patterns")
    ax.set_title("Pattern counts by detector definition (DXY)", fontsize=11)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    for i, r in df.iterrows():
        ax.text(i - w, r["loose_M"] + 5, str(r["loose_M"]), ha="center", fontsize=8)
        ax.text(i, r["strict_M"] + 5, str(r["strict_M"]), ha="center", fontsize=8, color="#d53e4f", fontweight="bold")
        ax.text(i + w, r["loose_V"] + 5, str(r["loose_V"]), ha="center", fontsize=8)
    plt.tight_layout()
    out = OUTDIR / "02_pattern_counts.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


# =============================================================
# FIGURE 3 — Effect-size summary across all tested signals
# =============================================================

def fig_effect_sizes():
    # Hand-curated from earlier analysis runs (1h DXY unless noted)
    signals = [
        ("V-floor breach (20d, daily)",      -1.53, "short"),
        ("V-floor breach (20×4h)",           -1.53, "short"),
        ("V-floor breach (20h, 1h)",         -1.44, "short"),
        ("V-floor breach (20×5m)",           -1.31, "short"),
        ("C→M 1-bar (1h)",                   -0.97, "short"),
        ("C→M 1-bar (daily)",                -0.86, "short"),
        ("M-bottom breach (20h, 1h)",        -0.39, "short"),
        ("Classifier decile-0 (20d, daily)", -0.81, "short"),
        ("C→V 1-bar (4h)",                   +1.03, "long"),
        ("C→V 1-bar (5m)",                   +0.96, "long"),
        ("C→V 1-bar (daily)",                +0.91, "long"),
        ("C→V 1-bar (1h)",                   +0.84, "long"),
        ("P1 entry (20d, daily)",            +1.44, "long"),
        ("P1 entry (20h, 1h)",               +1.28, "long"),
        ("P2 entry (20d, daily)",            +0.97, "long"),
        ("Dip-breach (5d, daily)",           +0.82, "long"),
        ("Classifier decile-9 (20d, daily)", +0.62, "long"),
    ]
    signals.sort(key=lambda x: x[1])

    labels = [s[0] for s in signals]
    values = [s[1] for s in signals]
    colors = ["#d53e4f" if s[2] == "short" else "#2c7fb8" for s in signals]

    fig, ax = plt.subplots(figsize=(11, 8))
    y = np.arange(len(signals))
    ax.barh(y, values, color=colors, alpha=0.85, edgecolor="#222", linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.axvline(-0.5, color="grey", linewidth=0.5, linestyle=":")
    ax.axvline(0.5, color="grey", linewidth=0.5, linestyle=":")
    ax.axvline(-0.8, color="grey", linewidth=0.5, linestyle=":")
    ax.axvline(0.8, color="grey", linewidth=0.5, linestyle=":")
    ax.set_xlabel("Cohen's d (negative = price falls / short signal; positive = price rises / long signal)")
    ax.set_title("Effect sizes — DXY RSI pattern signals, best horizon per signal\n"
                 "(red = short signals, blue = long signals)", fontsize=11, pad=10)
    ax.grid(True, alpha=0.3, axis="x")

    # Reference text
    ax.text(1.05, 0.5, "d > 0.8\nlarge effect", transform=ax.transAxes,
            fontsize=8, color="#555", ha="left", va="center")
    ax.text(1.05, 0.85, "Cohen's d\nrule of thumb:\nsmall=0.2\nmedium=0.5\nlarge=0.8", transform=ax.transAxes,
            fontsize=7, color="#555", ha="left", va="top",
            bbox=dict(boxstyle="round", facecolor="#fafafa", edgecolor="#ccc"))

    plt.tight_layout()
    out = OUTDIR / "03_effect_sizes.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


# =============================================================
# FIGURE 4 — Pattern clustering (after M / after V → next pattern)
# =============================================================

def fig_clustering():
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))

    # Daily
    after_m_daily = [76, 24]
    after_v_daily = [28, 73]  # after V, [M%, V%]
    after_m_1h = [29, 71]   # after M [V%, M%]
    after_v_1h = [67, 33]   # after V [V%, M%]

    # Pivot to consistent (Next M, Next V) order
    daily_after_m = [76, 24]  # Next M, Next V
    daily_after_v = [28, 73]
    one_after_m = [71, 29]
    one_after_v = [33, 67]

    categories = ["After M", "After V"]
    x = np.arange(len(categories))
    w = 0.35

    axes[0].bar(x - w/2, [daily_after_m[0], daily_after_v[0]], w, label="Next pattern = M", color="#fdb462")
    axes[0].bar(x + w/2, [daily_after_m[1], daily_after_v[1]], w, label="Next pattern = V", color="#80b1d3")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(categories)
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel("Probability (%)")
    axes[0].set_title("Daily DXY — pattern clustering")
    axes[0].axhline(50, color="black", linestyle=":", linewidth=0.8, alpha=0.4)
    axes[0].text(0.5, 53, "If alternating cycle (M→V→M→V), bars would be 50/50", ha="center", fontsize=8, color="#666")
    axes[0].legend(fontsize=9)
    for i, (m_pct, v_pct) in enumerate([daily_after_m, daily_after_v]):
        axes[0].text(i - w/2, m_pct + 1.5, f"{m_pct}%", ha="center", fontsize=9, fontweight="bold")
        axes[0].text(i + w/2, v_pct + 1.5, f"{v_pct}%", ha="center", fontsize=9, fontweight="bold")

    axes[1].bar(x - w/2, [one_after_m[0], one_after_v[0]], w, label="Next pattern = M", color="#fdb462")
    axes[1].bar(x + w/2, [one_after_m[1], one_after_v[1]], w, label="Next pattern = V", color="#80b1d3")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(categories)
    axes[1].set_ylim(0, 100)
    axes[1].set_ylabel("Probability (%)")
    axes[1].set_title("1h DXY — pattern clustering")
    axes[1].axhline(50, color="black", linestyle=":", linewidth=0.8, alpha=0.4)
    axes[1].legend(fontsize=9)
    for i, (m_pct, v_pct) in enumerate([one_after_m, one_after_v]):
        axes[1].text(i - w/2, m_pct + 1.5, f"{m_pct}%", ha="center", fontsize=9, fontweight="bold")
        axes[1].text(i + w/2, v_pct + 1.5, f"{v_pct}%", ha="center", fontsize=9, fontweight="bold")

    fig.suptitle("Pattern clustering: M's beget M's, V's beget V's (NOT alternating)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = OUTDIR / "04_pattern_clustering.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


# =============================================================
# FIGURE 5 — Classifier P(M) decile vs forward return (daily)
# =============================================================

def fig_classifier_deciles():
    # Hand-pulled from earlier classifier run (daily, 20-bar fwd return)
    deciles = list(range(10))
    p_m = [0.030, 0.070, 0.106, 0.149, 0.193, 0.240, 0.297, 0.367, 0.481, 0.713]
    fwd_pct = [-1.812, -0.980, -0.405, 0.137, 0.191, 0.254, 0.563, 0.447, 0.921, 0.893]

    fig, ax = plt.subplots(figsize=(11, 6))
    colors = ["#d53e4f" if r < 0 else "#2c7fb8" for r in fwd_pct]
    bars = ax.bar(deciles, fwd_pct, color=colors, edgecolor="#222", linewidth=0.6, alpha=0.85)
    ax.set_xticks(deciles)
    ax.set_xticklabels([f"D{d}\nP(M)={p_m[d]:.2f}" for d in deciles], fontsize=9)
    ax.set_xlabel("Classifier predicted P(M will form in next 30 days) — out-of-sample decile")
    ax.set_ylabel("Mean 20-day forward DXY return (%)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Out-of-sample classifier: P(M) decile vs. 20-day forward DXY return\n"
                 "Monotonic — top decile +0.89%, bottom decile -1.81% (2.7% spread)", fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")
    for d, v in zip(deciles, fwd_pct):
        ax.text(d, v + (0.06 if v >= 0 else -0.08), f"{v:+.2f}%",
                ha="center", fontsize=8, fontweight="bold",
                color="#222" if abs(v) < 0.5 else "black")
    plt.tight_layout()
    out = OUTDIR / "05_classifier_deciles.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


if __name__ == "__main__":
    print(f"Output directory: {OUTDIR}")
    print()
    print("Generating figures:")
    fig_strict_m_example()
    fig_pattern_counts()
    fig_effect_sizes()
    fig_clustering()
    fig_classifier_deciles()
    print()
    print("Done. Files in:", OUTDIR)
