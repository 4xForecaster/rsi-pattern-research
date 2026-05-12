#!/usr/bin/env python3
"""H15 — Cross-symbol validation of the two-layer M-P1 stack.

Tests whether the DXY-tuned rules (daily Scheme D from H12/H13 + 5m Scheme C
from H14) transfer to USDCHF and USDMXN.

Phase 1: data inventory (yfinance daily — no BarChart 5m for these symbols)
Phase 2: daily Scheme D per symbol, full sample + OOS slice (last 7 yrs)
         + USDCHF excl-2015 robustness check
Phase 3: 5m Scheme C — DOCUMENTED-BLOCKED for USDCHF/USDMXN (no data on disk)
Phase 4: comparison table DXY vs USDCHF vs USDMXN
Phase 5: go/no-go per symbol against documented thresholds
Phase 6: results writeup + equity figure
"""
from __future__ import annotations
import json
import pathlib
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import indicators, fld, position_sizing
from rsi_pattern import risk_metrics as rm

OUTDIR_FIG = REPO / "figures"
OUTDIR_FIG.mkdir(exist_ok=True)
CACHE_DIR = REPO / "data" / "yfinance_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# yfinance tickers per symbol (FX majors use Invert-convention; "CHF=X" is USDCHF)
TICKERS = {
    "DXY":    None,                  # use the existing BarChart CSV
    "USDCHF": "CHF=X",
    "USDMXN": "MXN=X",
}

# Scheme D — daily layer rules from H12/H13 v1.1
SCHEME_D = (0.0, 1.0, 3.0)   # bullish / neutral / bearish

# OOS split: last 7 years
OOS_YEARS = 7

# H14-style spread for daily (matches H12)
DAILY_SPREAD_BPS = 2.0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_yfinance_cached(ticker: str, start: str = "1990-01-01",
                         end: str = "2026-05-05") -> pd.DataFrame:
    """Cache yfinance daily downloads as CSV for reproducibility."""
    cache_path = CACHE_DIR / f"{ticker.replace('=','_').replace('^','')}_daily.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import yfinance as yf
        raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
    if raw.empty:
        raise RuntimeError(f"yfinance returned empty for {ticker!r}")
    # Flatten MultiIndex columns if present
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
    """Load existing DXY daily from the BarChart CSV path used by H12."""
    from rsi_pattern import data as data_mod
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy("daily")


# ---------------------------------------------------------------------------
# Daily backtest (Scheme D, loose-M, same as H12)
# ---------------------------------------------------------------------------

def run_daily_scheme_d(df: pd.DataFrame, *, label: str,
                       spread_bps: float = DAILY_SPREAD_BPS) -> dict:
    """Run the H12-equivalent daily Scheme D backtest. Returns metrics dict
    plus the equity curve and per-trade list."""
    df_rsi = indicators.add_rsi(df, period=14)
    bias = fld.fld_bias(df_rsi, cycles=(10, 20, 40))
    trades = position_sizing.fib_long_at_p1(df_rsi, rsi_col="rsi14")

    bull_m, neut_m, bear_m = SCHEME_D
    records = []
    bias_counts = {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        if lbl == "bullish":
            mult = bull_m
        elif lbl == "bearish":
            mult = bear_m
        else:
            mult = neut_m
        if mult == 0:
            continue
        records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(entry_ts),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    equity = rm.build_equity_curve(records, initial_capital=1.0, risk_per_trade=0.01)
    return {
        "label": label,
        "trades": len(records),
        "trade_universe": sum(1 for t in trades if t.r_multiple is not None),
        "bias_counts": bias_counts,
        "mean_R_weighted": float(np.mean([r.r_multiple * r.multiplier for r in records])) if records else float("nan"),
        "total_R_per_year": rm.total_r_per_year(records),
        "sharpe": rm.sharpe(equity),
        "sortino": rm.sortino(equity),
        "calmar": rm.calmar(equity),
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
        "data_first": df.index[0].date().isoformat(),
        "data_last": df.index[-1].date().isoformat(),
        "data_bars": len(df),
        "equity": equity,
        "records": records,
    }


# ---------------------------------------------------------------------------
# Go/No-Go decision rule
# ---------------------------------------------------------------------------

def go_no_go(metric: dict) -> tuple[str, str]:
    sortino = metric["sortino"]
    n = metric["trades"]
    if np.isnan(sortino):
        return "NO-GO", "Sortino undefined (likely too few/zero variance)"
    if sortino >= 3.0 and n >= 30:
        return "GO", f"Sortino {sortino:+.2f} ≥ 3.0 and trades {n} ≥ 30"
    if sortino < 1.0 or n < 10:
        return "NO-GO", f"Sortino {sortino:+.2f} < 1.0 OR trades {n} < 10 — needs symbol-specific calibration"
    return "SWEEP", f"Sortino {sortino:+.2f} in (1.0, 3.0) — run parameter sweep before deciding"


# ---------------------------------------------------------------------------
# Phase orchestration
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("PHASE 1 — Data inventory")
    print("=" * 70)
    data = {}
    data["DXY"]    = load_dxy_daily()
    data["USDCHF"] = load_yfinance_cached(TICKERS["USDCHF"])
    data["USDMXN"] = load_yfinance_cached(TICKERS["USDMXN"])
    for sym, df in data.items():
        print(f"  {sym:7s} daily | {len(df):>5d} bars | {df.index[0].date()} → {df.index[-1].date()}")
    print("\n  5m data: only present for DXY (BarChart CSV). USDCHF/USDMXN 5m unavailable.")

    print("\n" + "=" * 70)
    print("PHASE 2 — Daily Scheme D (loose-M, FLD 10/20/40, 0/1/3 mults)")
    print("=" * 70)

    results: dict[str, dict] = {}
    for sym, df in data.items():
        full = run_daily_scheme_d(df, label=f"{sym} full")
        # OOS: last 7 years
        cutoff = df.index[-1] - pd.Timedelta(days=int(OOS_YEARS * 365.25))
        df_oos = df[df.index >= cutoff]
        oos = run_daily_scheme_d(df_oos, label=f"{sym} OOS({OOS_YEARS}y)") if len(df_oos) > 200 else None

        rows = [full]
        if oos is not None:
            rows.append(oos)
        # USDCHF: also report excl-2015 (SNB franc-shock year)
        if sym == "USDCHF":
            mask = ~((df.index.year == 2015))
            df_excl15 = df[mask]
            rows.append(run_daily_scheme_d(df_excl15, label=f"{sym} excl-2015"))

        results[sym] = {"rows": rows, "df": df}
        print(f"\n--- {sym} ---")
        for r in rows:
            print(f"  {r['label']:<24} trades={r['trades']:>3} (universe={r['trade_universe']}, "
                  f"bias={r['bias_counts']}) "
                  f"meanR={r['mean_R_weighted']:>+6.2f} totR/yr={r['total_R_per_year']:>+6.2f} "
                  f"Sharpe={r['sharpe']:>+5.2f} Sortino={r['sortino']:>+5.2f} "
                  f"Calmar={r['calmar']:>+5.2f} MAR={r['mar']:>+5.2f} "
                  f"DD={r['max_dd']*100:>+6.2f}%")

    print("\n" + "=" * 70)
    print("PHASE 3 — 5m Scheme C")
    print("=" * 70)
    print("  SKIPPED: no 5m BarChart CSV present for USDCHF or USDMXN on this machine.")
    print("  DXY 5m results are unchanged from H14 (see results/H14_intraday_execution.md).")
    print("  When BarChart 5m data lands, re-run with scripts/h14_intraday_backtest.py")
    print("  pointed at the appropriate symbol CSV.")

    print("\n" + "=" * 70)
    print("PHASE 5 — Go / No-Go per symbol (daily layer)")
    print("=" * 70)
    decisions = {}
    for sym, blob in results.items():
        full_row = blob["rows"][0]
        decision, reason = go_no_go(full_row)
        decisions[sym] = (decision, reason, full_row)
        print(f"  {sym:7s}  {decision:<6s}  ({reason})")

    print("\n" + "=" * 70)
    print("PHASE 6 — Equity figure")
    print("=" * 70)
    fig, ax = plt.subplots(figsize=(12, 6.5))
    colors = {"DXY": "#888888", "USDCHF": "#377eb8", "USDMXN": "#e41a1c"}
    for sym, blob in results.items():
        eq = blob["rows"][0]["equity"]
        ax.plot(eq.index, eq.values, label=f"{sym} (daily, Scheme D)",
                color=colors[sym], linewidth=1.4)
    ax.axhline(1.0, color="black", linewidth=0.5, alpha=0.4)
    ax.set_title("H15 — Cross-symbol equity curves: daily Scheme D\n"
                 "1% risk per trade · loose-M · FLD (10,20,40) · 0/1/3 mults",
                 fontsize=11, pad=10)
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity (start = 1.0)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95)
    plt.tight_layout()
    out = OUTDIR_FIG / "10_cross_symbol_equity.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  Wrote {out}")

    # Persist a JSON dump for the writeup
    serializable = {}
    for sym, blob in results.items():
        serializable[sym] = {
            "rows": [
                {k: (v if not isinstance(v, (pd.Series, list)) else None)
                 for k, v in r.items() if k not in ("equity", "records")}
                for r in blob["rows"]
            ],
            "decision": decisions[sym][0],
            "decision_reason": decisions[sym][1],
        }
    json_path = REPO / "results" / "_h15_run.json"
    json_path.write_text(json.dumps(serializable, indent=2, default=str))
    print(f"  Wrote {json_path}")

    return results, decisions


if __name__ == "__main__":
    main()
