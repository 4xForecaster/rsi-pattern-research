#!/usr/bin/env python3
"""H12 — Risk-adjusted metrics across the 5 hybrid position-sizing schemes.

Regenerates the H11 trade list (M-P1 LONG entries on daily DXY), tags each
trade with its FLD bias at entry, applies each scheme's bullish/neutral/
bearish multiplier, and computes a proper Sharpe / Sortino / MAR / Calmar
from the resulting daily equity curve.

Outputs:
- prints comparison table to stdout
- writes figures/08_equity_curves_risk_adjusted.png
"""
from __future__ import annotations
import pathlib, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import data as data_mod
from rsi_pattern import indicators, fld, position_sizing
from rsi_pattern import risk_metrics as rm

# Allow override of data root (mirrors the convention in generate_synopsis_figures.py)
DEFAULT_DATA_ROOT = pathlib.Path.home() / "Documents" / "rsi-data"
if DEFAULT_DATA_ROOT.exists():
    data_mod.DATA_DIR = DEFAULT_DATA_ROOT

OUTDIR = REPO / "figures"
OUTDIR.mkdir(exist_ok=True)

# bullish / neutral / bearish multipliers at FLD bias of entry
SCHEMES = {
    "A. Pure parallel (1/1/1)":      (1.0, 1.0, 1.0),
    "B. Modest (1/1/3)":             (1.0, 1.0, 3.0),
    "C. Aggressive (1/1/5)":         (1.0, 1.0, 5.0),
    "D. Skip bullish + 3x (0/1/3)":  (0.0, 1.0, 3.0),
    "E. Conservative (0.5/1/3)":     (0.5, 1.0, 3.0),
}

SCHEME_COLORS = {
    "A. Pure parallel (1/1/1)":      "#888888",
    "B. Modest (1/1/3)":             "#4daf4a",
    "C. Aggressive (1/1/5)":         "#e41a1c",
    "D. Skip bullish + 3x (0/1/3)":  "#377eb8",
    "E. Conservative (0.5/1/3)":     "#984ea3",
}


def build_trades_with_bias():
    """Generate the 124 M-P1 LONG trades and tag each with FLD bias at entry."""
    df = indicators.add_rsi(data_mod.load_dxy("daily"))
    bias = fld.fld_bias(df)  # uses canonical 10/20/40 cycles
    trades = position_sizing.fib_long_at_p1(df, rsi_col="rsi14")

    tagged = []
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        entry_ts = df.index[t.entry_idx]
        label = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        tagged.append((t, label))
    return df, tagged


def multipliers_for_scheme(tagged_trades, scheme: tuple[float, float, float]):
    """Return a list of per-trade multipliers under the given scheme."""
    bull_m, neut_m, bear_m = scheme
    out = []
    for _, label in tagged_trades:
        if label == "bullish":
            out.append(bull_m)
        elif label == "bearish":
            out.append(bear_m)
        else:
            out.append(neut_m)  # neutral or unknown
    return out


def format_pct(x: float) -> str:
    return f"{x * 100:+.2f}%" if not (isinstance(x, float) and np.isnan(x)) else "n/a"


def format_num(x: float, decimals: int = 2) -> str:
    if isinstance(x, float) and np.isnan(x):
        return "n/a"
    return f"{x:+.{decimals}f}"


def main():
    df, tagged = build_trades_with_bias()
    bias_counts = pd.Series([lbl for _, lbl in tagged]).value_counts().to_dict()
    print(f"Loaded {len(df)} daily DXY bars from "
          f"{df.index[0].date()} to {df.index[-1].date()}")
    print(f"Generated {len(tagged)} completed M-P1 LONG trades")
    print(f"FLD bias at entry: {bias_counts}")
    print()

    summaries: list[dict] = []
    equity_curves: dict[str, pd.Series] = {}
    for name, scheme in SCHEMES.items():
        mults = multipliers_for_scheme(tagged, scheme)
        trade_records = rm.trades_from_fib(
            [t for (t, _) in tagged],
            df_index=df.index,
            multipliers=mults,
        )
        equity = rm.build_equity_curve(trade_records, initial_capital=1.0, risk_per_trade=0.01)
        equity_curves[name] = equity
        summaries.append(rm.summarize(name, trade_records, equity))

    # Print comparison table
    cols = ["scheme", "trades", "mean_R", "total_R_per_year",
            "sharpe", "sortino", "calmar", "mar", "max_dd"]
    headers = ["Scheme", "Trades", "Mean R", "Total R/yr",
               "Sharpe", "Sortino", "Calmar", "MAR", "Max DD"]
    rows = []
    for s in summaries:
        rows.append([
            s["scheme"],
            f"{s['trades']:d}",
            format_num(s["mean_R"], 2),
            format_num(s["total_R_per_year"], 2),
            format_num(s["sharpe"], 2),
            format_num(s["sortino"], 2),
            format_num(s["calmar"], 2),
            format_num(s["mar"], 2),
            format_pct(s["max_dd"]),
        ])

    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    fmt = " | ".join(f"{{:<{w}}}" for w in widths)
    sep = "-+-".join("-" * w for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for r in rows:
        print(fmt.format(*r))
    print()

    # Save figure: equity curves
    fig, ax = plt.subplots(figsize=(12, 6.5))
    for name, eq in equity_curves.items():
        ax.plot(eq.index, eq.values, label=name, color=SCHEME_COLORS[name], linewidth=1.4)
    ax.axhline(1.0, color="black", linewidth=0.6, alpha=0.4)
    ax.set_title("H12 — Equity curves by FLD-scaled position-sizing scheme\n"
                 "1% capital risked per 1x trade · daily DXY · M-P1 LONG entries",
                 fontsize=11, pad=10)
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity (start = 1.0)")
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    out = OUTDIR / "08_equity_curves_risk_adjusted.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out}")

    return summaries, equity_curves


if __name__ == "__main__":
    main()
