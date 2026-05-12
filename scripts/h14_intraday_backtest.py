#!/usr/bin/env python3
"""H14 — Intraday port of M-P1 strategy to 5m and 15m DXY with strict-M.

Phases (run sequentially when invoked with no args, individually with flags):
  1.4: range-lookback sensitivity sweep (0.5x / 1x / 2x of longest FLD cycle)
  2.5: 5-scheme position-sizing sweep (A/B/C/D/E) per timeframe
  2.7: 3-knob ablation on the winning scheme
  3.11: equity curve figure

All cells share Scheme D defaults except the swept variable.
"""
from __future__ import annotations
import argparse, json, pathlib, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import data as data_mod
from rsi_pattern import indicators, fld
from rsi_pattern import intraday as itd
from rsi_pattern import risk_metrics as rm

DEFAULT_DATA_ROOT = pathlib.Path.home() / "Documents" / "rsi-data"
if DEFAULT_DATA_ROOT.exists():
    data_mod.DATA_DIR = DEFAULT_DATA_ROOT

OUTDIR_FIG = REPO / "figures"
OUTDIR_FIG.mkdir(exist_ok=True)

# Annualization factors (bars/year): FX 252 trading days × intraday bars/day
PERIODS_PER_YEAR = {
    "5m":  252 * 288,   # 72,576
    "15m": 252 * 96,    # 24,192
}

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


def resample_15m(df5: pd.DataFrame) -> pd.DataFrame:
    return df5.resample("15min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()


def load_intraday():
    df5_raw = data_mod.load_dxy("5m")
    df5 = indicators.add_rsi(df5_raw)
    df5["atr14"] = itd.atr14(df5)
    df15_raw = resample_15m(df5_raw)
    df15 = indicators.add_rsi(df15_raw)
    df15["atr14"] = itd.atr14(df15)
    return df5, df15


def multipliers_from_scheme(trades, bias_df, scheme):
    bull_m, neut_m, bear_m = scheme
    mults = []
    for t in trades:
        ts = bias_df.index[t.entry_idx] if t.entry_idx < len(bias_df.index) else None
        lbl = bias_df.loc[ts, "bias_label"] if ts is not None and ts in bias_df.index else "unknown"
        if lbl == "bullish":
            mults.append(bull_m)
        elif lbl == "bearish":
            mults.append(bear_m)
        else:
            mults.append(neut_m)
    return mults


def metrics_from_records(records, bar_close, ppy, name="cell"):
    equity = rm.build_equity_curve_mtm(records, bar_close, initial_capital=1.0, risk_per_trade=0.01)
    return {
        "scheme": name,
        "trades": len(records),
        "mean_R_weighted": float(np.mean([r.r_multiple * r.multiplier for r in records])) if records else float("nan"),
        "total_R_per_year": rm.total_r_per_year(records),
        "sharpe": rm.sharpe(equity, periods_per_year=ppy),
        "sortino": rm.sortino(equity, periods_per_year=ppy),
        "calmar": rm.calmar(equity, window_years=0.25),  # 3 months ≈ 0.25y on this short window
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
    }, equity


def build_scheme_records(df, fib_trades, scheme, spread):
    bias = fld.fld_bias(df, cycles=itd.INTRADAY_FLD_CYCLES["5m" if df is not None and len(df) > 10000 else "15m"])
    # Re-compute bias with correct cycles based on bar density
    # (caller should pass the right cycles; here we infer from df length as a fallback)
    mults = multipliers_from_scheme(fib_trades, bias, scheme)
    # Convert FibTrade list → r_multiple records first (for mean_R / total_R/yr)
    records = []
    for t, mult in zip(fib_trades, mults):
        if t.exit_idx is None or t.r_multiple is None or mult == 0:
            continue
        records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(df.index[t.entry_idx]),
            exit_date=pd.Timestamp(df.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    mtm_records = itd.fib_to_mtm(fib_trades, df, mults, spread)
    return records, mtm_records


def run_for_tf(label, df, lookback_bars, detector="strict", range_rule="pre_p1", stop_rule="structural"):
    """Generate FibTrades + cycle-correct FLD bias for one TF/config."""
    cycles = itd.INTRADAY_FLD_CYCLES[label]
    bias = fld.fld_bias(df, cycles=cycles)
    fib_trades = itd.build_fib_trades(
        df,
        detector=detector,
        range_rule=range_rule,
        lookback_bars=lookback_bars,
        stop_rule=stop_rule,
        time_stop_bars=itd.INTRADAY_TIME_STOP_BARS[label],
        atr_series=df.get("atr14"),
    )
    return fib_trades, bias


def summarize_scheme(label, df, fib_trades, bias, scheme, scheme_name, ppy, spread):
    mults = multipliers_from_scheme(fib_trades, bias, scheme)
    # R-records (for mean R / total R/yr)
    r_records = []
    for t, mult in zip(fib_trades, mults):
        if t.exit_idx is None or t.r_multiple is None or mult == 0:
            continue
        r_records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(df.index[t.entry_idx]),
            exit_date=pd.Timestamp(df.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    mtm_records = itd.fib_to_mtm(fib_trades, df, mults, spread)
    equity = rm.build_equity_curve_mtm(mtm_records, df["close"], initial_capital=1.0, risk_per_trade=0.01)
    return {
        "scheme": scheme_name,
        "trades": len(r_records),
        "mean_R_weighted": float(np.mean([r.r_multiple * r.multiplier for r in r_records])) if r_records else float("nan"),
        "total_R_per_year": rm.total_r_per_year(r_records),
        "sharpe": rm.sharpe(equity, periods_per_year=ppy),
        "sortino": rm.sortino(equity, periods_per_year=ppy),
        "calmar": rm.calmar(equity, window_years=0.25),
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
    }, equity


# ---------- Phase 1.4: range lookback sensitivity sweep ----------

def phase_1_4_range_lookback(df5, df15):
    print("=" * 70)
    print("PHASE 1.4 — Range lookback sensitivity (Scheme D, strict-M, structural stop)")
    print("=" * 70)
    out = {}
    for label, df in [("5m", df5), ("15m", df15)]:
        base = itd.INTRADAY_FLD_CYCLES[label][-1]   # longest cycle
        ppy = PERIODS_PER_YEAR[label]
        sweep = [("0.5x", base // 2), ("1x", base), ("2x", base * 2)]
        rows = []
        for lab, lb in sweep:
            fib_trades, bias = run_for_tf(label, df, lookback_bars=lb)
            s, _ = summarize_scheme(label, df, fib_trades, bias, SCHEMES["D. Skip bullish + 3x (0/1/3)"],
                                     f"{label} lookback={lb}", ppy, itd.INTRADAY_SPREAD[label])
            s["lookback_bars"] = lb
            s["lookback_label"] = lab
            rows.append(s)
        out[label] = rows
        print(f"\n--- {label} ---")
        for r in rows:
            print(f"  lookback {r['lookback_label']:>4} ({r['lookback_bars']:>3} bars): "
                  f"trades={r['trades']:>3} meanR={r['mean_R_weighted']:+.2f} "
                  f"Sharpe={r['sharpe']:+.2f} Sortino={r['sortino']:+.2f} "
                  f"MaxDD={r['max_dd']*100:+.2f}% TotalR/yr={r['total_R_per_year']:+.2f}")
    return out


# ---------- Phase 2.5: 5-scheme sweep ----------

def phase_2_5_schemes(df5, df15, lookbacks):
    """lookbacks: {'5m': N, '15m': N} chosen from phase 1.4."""
    print("\n" + "=" * 70)
    print("PHASE 2.5 — 5-scheme position-sizing sweep (intraday)")
    print("=" * 70)
    out = {}
    for label, df in [("5m", df5), ("15m", df15)]:
        lb = lookbacks[label]
        ppy = PERIODS_PER_YEAR[label]
        spread = itd.INTRADAY_SPREAD[label]
        fib_trades, bias = run_for_tf(label, df, lookback_bars=lb)
        bias_counts = pd.Series([
            bias.loc[df.index[t.entry_idx], "bias_label"] if df.index[t.entry_idx] in bias.index else "unknown"
            for t in fib_trades if t.r_multiple is not None
        ]).value_counts().to_dict()
        print(f"\n--- {label} (lookback={lb}) ---")
        print(f"  trade universe: {sum(1 for t in fib_trades if t.r_multiple is not None)} "
              f"completed strict-M trades; FLD bias: {bias_counts}")
        rows = []
        for name, scheme in SCHEMES.items():
            s, eq = summarize_scheme(label, df, fib_trades, bias, scheme, name, ppy, spread)
            s["equity"] = eq
            rows.append(s)
        out[label] = {"rows": rows, "bias_counts": bias_counts, "fib_trades": fib_trades, "bias": bias}
        print(f"  {'Scheme':<32} {'Tr':>3} {'MeanR':>7} {'R/yr':>7} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} {'MAR':>7} {'MaxDD':>7}")
        for r in rows:
            print(f"  {r['scheme']:<32} {r['trades']:>3} "
                  f"{r['mean_R_weighted']:>+7.2f} {r['total_R_per_year']:>+7.2f} "
                  f"{r['sharpe']:>+7.2f} {r['sortino']:>+8.2f} {r['calmar']:>+7.2f} {r['mar']:>+7.2f} "
                  f"{r['max_dd']*100:>+6.2f}%")
    return out


def pick_winner(rows):
    """Highest Sortino among rows with ≥20 trades; 5% tie-break on Mean R, then trade count."""
    valid = [r for r in rows if r["trades"] >= 20 and not np.isnan(r["sortino"])]
    if not valid:
        # Relax threshold if no cell has ≥20 trades
        valid = [r for r in rows if r["trades"] >= 5 and not np.isnan(r["sortino"])]
    if not valid:
        return None
    valid.sort(key=lambda r: -r["sortino"])
    top = valid[0]["sortino"]
    near = [r for r in valid if abs(r["sortino"] - top) / abs(top + 1e-9) <= 0.05]
    if len(near) > 1:
        near.sort(key=lambda r: (-r["mean_R_weighted"], -r["trades"]))
        return near[0]
    return valid[0]


# ---------- Phase 2.7: 3-knob ablation on the winning scheme ----------

ABLATION_CELLS = [
    # (label, detector, range_rule, stop_rule)
    ("baseline (strict/struct/pre-P1)", "strict", "pre_p1",   "structural"),
    ("v1 loose-M",                       "loose",  "pre_p1",   "structural"),
    ("v2 wider stop (ATR)",              "strict", "pre_p1",   "wider_atr"),
    ("v3 pre-entry range",               "strict", "pre_entry","structural"),
    ("v_all (loose+wider+pre-entry)",    "loose",  "pre_entry","wider_atr"),
]


def phase_2_7_ablation(df5, df15, winning_scheme, winning_scheme_name, lookbacks):
    print("\n" + "=" * 70)
    print(f"PHASE 2.7 — 3-knob ablation on {winning_scheme_name}")
    print("=" * 70)
    out = {}
    for label, df in [("5m", df5), ("15m", df15)]:
        lb = lookbacks[label]
        ppy = PERIODS_PER_YEAR[label]
        spread = itd.INTRADAY_SPREAD[label]
        rows = []
        for cell_label, det, range_rule, stop_rule in ABLATION_CELLS:
            fib_trades, bias = run_for_tf(label, df, lookback_bars=lb,
                                           detector=det, range_rule=range_rule, stop_rule=stop_rule)
            s, _ = summarize_scheme(label, df, fib_trades, bias, winning_scheme, cell_label, ppy, spread)
            rows.append(s)
        out[label] = rows
        print(f"\n--- {label} ---")
        print(f"  {'Cell':<38} {'Tr':>3} {'MeanR':>7} {'R/yr':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>7}")
        for r in rows:
            print(f"  {r['scheme']:<38} {r['trades']:>3} "
                  f"{r['mean_R_weighted']:>+7.2f} {r['total_R_per_year']:>+7.2f} "
                  f"{r['sharpe']:>+7.2f} {r['sortino']:>+8.2f} {r['max_dd']*100:>+6.2f}%")
    return out


# ---------- Equity curve figure ----------

def make_equity_figure(scheme_results):
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=False)
    for ax, label in zip(axes, ["5m", "15m"]):
        rows = scheme_results[label]["rows"]
        for r in rows:
            eq = r["equity"]
            ax.plot(eq.index, eq.values, label=r["scheme"],
                    color=SCHEME_COLORS[r["scheme"]], linewidth=1.2)
        ax.axhline(1.0, color="black", linewidth=0.5, alpha=0.4)
        ax.set_title(f"H14 — {label} DXY · 5-scheme equity curves (overlap-aware MTM, "
                     f"spread={itd.INTRADAY_SPREAD[label]*1e4:.1f} bps)",
                     fontsize=10, pad=8)
        ax.set_ylabel("Equity (start=1.0)")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left", fontsize=8, framealpha=0.95)
    plt.tight_layout()
    out = OUTDIR_FIG / "09_intraday_equity_curves.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {out}")
    return out


# ---------- Main ----------

def main():
    df5, df15 = load_intraday()
    print(f"5m  loaded: {len(df5)} bars  {df5.index[0]} → {df5.index[-1]}")
    print(f"15m loaded: {len(df15)} bars  {df15.index[0]} → {df15.index[-1]}")

    # Phase 1.4
    lb_results = phase_1_4_range_lookback(df5, df15)
    # Pick best lookback per TF by Sortino (Scheme D)
    chosen = {}
    for tf, rows in lb_results.items():
        valid = [r for r in rows if not np.isnan(r["sortino"])]
        if not valid:
            chosen[tf] = itd.INTRADAY_FLD_CYCLES[tf][-1]  # fallback to 1x
            continue
        valid.sort(key=lambda r: -r["sortino"])
        chosen[tf] = valid[0]["lookback_bars"]
    print(f"\nChosen lookbacks: {chosen}")

    # Phase 2.5
    scheme_results = phase_2_5_schemes(df5, df15, chosen)

    # Pick winner per TF
    winners = {}
    for tf, blob in scheme_results.items():
        w = pick_winner([r for r in blob["rows"]])
        winners[tf] = w
        if w:
            print(f"\nWinner ({tf}): {w['scheme']} — Sortino {w['sortino']:+.2f}, "
                  f"Mean R {w['mean_R_weighted']:+.2f}, {w['trades']} trades")
        else:
            print(f"\nNo valid winner on {tf} — too few trades")

    # Pick global winner (use 5m winner as the primary)
    primary = winners.get("5m") or winners.get("15m")
    primary_scheme = SCHEMES.get(primary["scheme"]) if primary else SCHEMES["D. Skip bullish + 3x (0/1/3)"]
    primary_name = primary["scheme"] if primary else "D. Skip bullish + 3x (0/1/3)"

    # Phase 2.7 — ablation on winner
    ablation_results = phase_2_7_ablation(df5, df15, primary_scheme, primary_name, chosen)

    # Equity figure
    fig_path = make_equity_figure(scheme_results)

    # Dump JSON for downstream writeup
    out_json = {
        "data_window": {
            "5m": [str(df5.index[0]), str(df5.index[-1]), len(df5)],
            "15m": [str(df15.index[0]), str(df15.index[-1]), len(df15)],
        },
        "fld_cycles": itd.INTRADAY_FLD_CYCLES,
        "time_stop_bars": itd.INTRADAY_TIME_STOP_BARS,
        "spread": itd.INTRADAY_SPREAD,
        "strict_cfg": {
            "rise_origin_below": itd.INTRADAY_STRICT_CFG.rise_origin_below,
            "major_peak_min": itd.INTRADAY_STRICT_CFG.major_peak_min,
            "wiggle_trough_floor": itd.INTRADAY_STRICT_CFG.wiggle_trough_floor,
            "completion_threshold": itd.INTRADAY_STRICT_CFG.completion_threshold,
        },
        "phase_1_4": {tf: [{k: (v if not isinstance(v, float) or not np.isnan(v) else None)
                            for k, v in r.items()} for r in rows]
                      for tf, rows in lb_results.items()},
        "chosen_lookbacks": chosen,
        "phase_2_5": {tf: [{k: (v if not isinstance(v, float) or not np.isnan(v) else None)
                            for k, v in r.items() if k != "equity"} for r in blob["rows"]]
                      for tf, blob in scheme_results.items()},
        "bias_counts": {tf: blob["bias_counts"] for tf, blob in scheme_results.items()},
        "winners": {tf: (w["scheme"] if w else None) for tf, w in winners.items()},
        "phase_2_7": {tf: [{k: (v if not isinstance(v, float) or not np.isnan(v) else None)
                            for k, v in r.items()} for r in rows]
                      for tf, rows in ablation_results.items()},
    }
    json_path = REPO / "results" / "_h14_run.json"
    json_path.write_text(json.dumps(out_json, indent=2, default=str))
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
