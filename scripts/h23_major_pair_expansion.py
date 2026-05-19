#!/usr/bin/env python3
"""H23 — Major-pair expansion of the daily Scheme D regime layer.

Question (the ONLY question): does the DXY-calibrated daily Scheme D
framework transfer, unchanged, to the remaining FX majors?

No parameter re-tuning. Every symbol runs the *identical* engine that is
live for DXY via hurst-agent cron:

    indicators.add_rsi(df, 14)
    position_sizing.fib_long_at_p1(df, cfg=PatternConfig())   # loose-M, dip=50
    fld.fld_bias(df, cycles=(10, 20, 40))
    Scheme D sizing: bullish 0x / neutral 1x / bearish 3x  (at entry bar)
    rm.build_equity_curve -> rm.sortino / rm.max_drawdown

`run_one` below is lifted verbatim from scripts/h16_usdmxn_calibration.py so
the metric computation is the same code path that produced the recorded
DXY (+5.75 / 56) and USDMXN (+4.41 / 26) numbers — this is a transfer test,
not a reimplementation.

Methodology (inherited from H16, the canonical protocol):
  * 70/30 chronological split BY BARS: IS = first 70%, OOS = last 30%.
  * OOS metrics are load-bearing. Full-sample is reported for context only,
    EXCEPT the trade-count floor, which is applied to the full sample
    (the "PRAGMATIC" reading H16 used and how USDMXN/DXY were recorded:
    "H15 full-sample: ... 26 trades (below 30-trade floor)").

Decision rule (task-locked thresholds, mapped onto H16's OOS protocol):
  GO    : OOS Sortino >= 3.0 AND full-sample trades >= 30
  NO-GO : OOS Sortino <  1.0 OR  full-sample trades < 10
  SWEEP : anything in between
OOS MaxDD is reported alongside for transparency (H16 also gated on it; we
report it but the GO/SWEEP/NO-GO *label* follows the task-locked Sortino /
trade-count thresholds only).

Dislocation robustness: for symbols with a known structural shock we also
report full-sample metrics with the shock calendar year(s) removed:
  USDJPY : BOJ / MoF intervention years {2003, 2004, 2011, 2022, 2024}
  AUDUSD : 2008 GFC carry unwind {2008}
  GBPUSD : Brexit {2016}

Deliverable numbering note (load-bearing decision): the task brief asked
for results/H17_* and figures/11_*,12_*. Those slots are already occupied
in this repo (H17 = walk-forward strict-M; figure 11 = H22 V-floor short).
Overwriting them would destroy prior committed work and is a no-history-
rewrite violation, so this experiment ships as H23 with figures 12 & 13.
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

OUTDIR_FIG = REPO / "figures"
OUTDIR_FIG.mkdir(exist_ok=True)
CACHE_DIR = REPO / "data" / "yfinance_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Deterministic pipeline (no RNG in detect_m / fib / fld / sortino), but we
# pin a seed per Anthropic reproducibility practice so any future stochastic
# addition stays reproducible.
SEED = 4242

SCHEME_D = (0.0, 1.0, 3.0)  # bullish / neutral / bearish — DXY-calibrated
IS_FRACTION = 0.70
DAILY_SPREAD_BPS = 2.0  # parity with H12/H15 (spread is inside r_multiple? no
#                          — kept here only for the writeup; rm uses r_multiple
#                          which already nets simulate_fib_trade exits).

# yfinance tickers — from hurst-agent/config/symbols.yaml (fx_major block).
# DXY uses the BarChart daily CSV (same path H12/H15 used) so the reference
# number reproduces exactly.
YF_TICKERS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
}

# Known structural dislocations — calendar years removed for the robustness row.
DISLOCATION_YEARS = {
    "USDJPY": {2003, 2004, 2011, 2022, 2024},  # MoF/BOJ intervention episodes
    "AUDUSD": {2008},                          # GFC carry unwind
    "GBPUSD": {2016},                          # Brexit referendum + Oct flash crash
}

YF_END = "2026-05-19"  # pinned for reproducibility (today)


# ---------------------------------------------------------------------------
# Data loading (cached for reproducibility, keyed by ticker)
# ---------------------------------------------------------------------------

def load_yfinance_cached(ticker: str, start: str = "1990-01-01",
                         end: str = YF_END) -> pd.DataFrame:
    """Cache yfinance daily downloads as CSV. Same loader shape as H15."""
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
    if len(df) < 250:
        raise RuntimeError(
            f"{ticker!r}: only {len(df)} clean bars — refusing to fake a "
            f"backtest on a stub history. Documented + skipped."
        )
    df.to_csv(cache_path)
    return df


def load_dxy_daily() -> pd.DataFrame:
    """DXY reference — BarChart daily CSV, identical path to H12/H15."""
    from rsi_pattern import data as data_mod
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy("daily")


# ---------------------------------------------------------------------------
# Engine — lifted verbatim from h16_usdmxn_calibration.run_one
# ---------------------------------------------------------------------------

def run_one(df: pd.DataFrame, *, dip: float, cycles: tuple, label: str) -> dict:
    df_rsi = indicators.add_rsi(df, period=14)
    cfg = PatternConfig(m_inner_threshold=dip)
    trades = position_sizing.fib_long_at_p1(df_rsi, rsi_col="rsi14", cfg=cfg)
    bias = fld.fld_bias(df_rsi, cycles=cycles)

    bull_m, neut_m, bear_m = SCHEME_D
    records = []
    bias_counts = {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    universe = 0
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        universe += 1
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
        "universe": universe,
        "bias_counts": bias_counts,
        "mean_R_weighted": float(np.mean([r.r_multiple * r.multiplier for r in records])) if records else float("nan"),
        "total_R_per_year": rm.total_r_per_year(records),
        "sharpe": rm.sharpe(equity),
        "sortino": rm.sortino(equity),
        "calmar": rm.calmar(equity),
        "mar": rm.mar(equity),
        "max_dd": rm.max_drawdown(equity),
        "equity": equity,
    }


# ---------------------------------------------------------------------------
# Decision rule — task-locked thresholds on H16's OOS protocol
# ---------------------------------------------------------------------------

def go_no_go(oos: dict, full: dict) -> tuple[str, str]:
    s = oos["sortino"]
    full_n = full["trades"]
    oos_n = oos["trades"]
    if np.isnan(s):
        return "NO-GO", f"OOS Sortino undefined (OOS trades={oos_n}) — no transfer"
    if s >= 3.0 and full_n >= 30:
        return "GO", (f"OOS Sortino {s:+.2f} >= 3.0 AND full trades {full_n} >= 30 "
                      f"(OOS trades={oos_n}, OOS MaxDD={oos['max_dd']*100:+.1f}%)")
    if s < 1.0 or full_n < 10:
        return "NO-GO", (f"OOS Sortino {s:+.2f} < 1.0 OR full trades {full_n} < 10 "
                         f"— framework does not transfer")
    return "SWEEP", (f"OOS Sortino {s:+.2f} in [1.0, 3.0) or trade-count short "
                     f"(full={full_n}, OOS={oos_n}) — sweep before deciding")


def split_70_30(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(df)
    is_end = int(n * IS_FRACTION)
    return df.iloc[:is_end], df.iloc[is_end:]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def evaluate_symbol(sym: str, df: pd.DataFrame) -> dict:
    np.random.seed(SEED)  # determinism guard (pipeline is already deterministic)
    df_is, df_oos = split_70_30(df)
    full = run_one(df, dip=50.0, cycles=(10, 20, 40), label=f"{sym} FULL")
    is_m = run_one(df_is, dip=50.0, cycles=(10, 20, 40), label=f"{sym} IS")
    oos = run_one(df_oos, dip=50.0, cycles=(10, 20, 40), label=f"{sym} OOS")
    decision, reason = go_no_go(oos, full)

    disloc = None
    if sym in DISLOCATION_YEARS:
        yrs = DISLOCATION_YEARS[sym]
        mask = ~df.index.year.isin(list(yrs))
        df_x = df[mask]
        disloc = run_one(df_x, dip=50.0, cycles=(10, 20, 40),
                         label=f"{sym} excl-{sorted(yrs)}")
        disloc["excluded_years"] = sorted(yrs)

    return {
        "symbol": sym,
        "data_first": df.index[0].date().isoformat(),
        "data_last": df.index[-1].date().isoformat(),
        "data_bars": len(df),
        "is_window": [df_is.index[0].date().isoformat(),
                      df_is.index[-1].date().isoformat(), len(df_is)],
        "oos_window": [df_oos.index[0].date().isoformat(),
                       df_oos.index[-1].date().isoformat(), len(df_oos)],
        "full": full, "is": is_m, "oos": oos, "disloc": disloc,
        "decision": decision, "decision_reason": reason,
    }


def _clean(m: Optional[dict]) -> Optional[dict]:
    if m is None:
        return None
    return {k: v for k, v in m.items() if k != "equity"}


def main() -> None:
    print("=" * 78)
    print("H23 — Major-pair expansion: does DXY-calibrated daily Scheme D transfer?")
    print("=" * 78)

    data: dict[str, pd.DataFrame] = {}
    skipped: dict[str, str] = {}

    # DXY reference (BarChart daily CSV — reproduces the +5.75/56 anchor)
    try:
        data["DXY"] = load_dxy_daily()
    except Exception as e:  # noqa: BLE001
        skipped["DXY"] = f"DXY reference load failed: {e}"

    for sym, tkr in YF_TICKERS.items():
        try:
            data[sym] = load_yfinance_cached(tkr)
        except Exception as e:  # noqa: BLE001
            skipped[sym] = f"{tkr}: {e}"
            print(f"  [SKIP] {sym}: {e}")

    print("\nPHASE 1 — Data inventory")
    for sym, df in data.items():
        print(f"  {sym:7s} | {len(df):>5d} bars | "
              f"{df.index[0].date()} -> {df.index[-1].date()}")
    for sym, why in skipped.items():
        print(f"  {sym:7s} | SKIPPED — {why}")

    print("\nPHASE 2 — Per-symbol 70/30 IS/OOS evaluation (DXY params, no re-tune)")
    results: dict[str, dict] = {}
    for sym, df in data.items():
        r = evaluate_symbol(sym, df)
        results[sym] = r
        print(f"\n--- {sym} --- ({r['data_first']} -> {r['data_last']}, "
              f"{r['data_bars']} bars)")
        print(f"  IS  {r['is_window'][0]}->{r['is_window'][1]} ({r['is_window'][2]} bars)")
        print(f"  OOS {r['oos_window'][0]}->{r['oos_window'][1]} ({r['oos_window'][2]} bars)")
        for tag in ("is", "oos", "full"):
            m = r[tag]
            print(f"   {tag.upper():4s} trades={m['trades']:>3} (univ={m['universe']:>3}) "
                  f"meanR={m['mean_R_weighted']:>+6.2f} R/yr={m['total_R_per_year']:>+6.2f} "
                  f"Sharpe={m['sharpe']:>+5.2f} Sortino={m['sortino']:>+6.2f} "
                  f"MaxDD={m['max_dd']*100:>+6.1f}%")
        if r["disloc"] is not None:
            m = r["disloc"]
            print(f"   DISLOC excl-{m['excluded_years']}: full trades={m['trades']} "
                  f"Sortino={m['sortino']:>+6.2f} MaxDD={m['max_dd']*100:>+6.1f}%")
        print(f"   => {r['decision']}  ({r['decision_reason']})")

    print("\nPHASE 3 — Comparison table (sorted by OOS Sortino)")
    order = sorted(results.values(),
                   key=lambda r: (-1e9 if np.isnan(r["oos"]["sortino"])
                                  else r["oos"]["sortino"]),
                   reverse=True)
    hdr = (f"{'Symbol':<8}{'Decision':<8}{'OOS Sortino':>12}{'OOS Tr':>8}"
           f"{'Full Tr':>9}{'OOS MaxDD':>11}{'Full Sortino':>14}")
    print(hdr)
    print("-" * len(hdr))
    for r in order:
        print(f"{r['symbol']:<8}{r['decision']:<8}"
              f"{r['oos']['sortino']:>+12.2f}{r['oos']['trades']:>8}"
              f"{r['full']['trades']:>9}{r['oos']['max_dd']*100:>+10.1f}%"
              f"{r['full']['sortino']:>+14.2f}")

    # DXY foundation check
    if "DXY" in results:
        dxy_full = results["DXY"]["full"]
        print(f"\nFOUNDATION CHECK — DXY full-sample: Sortino "
              f"{dxy_full['sortino']:+.2f} / {dxy_full['trades']} trades "
              f"(recorded anchor: +5.75 / 56). "
              f"{'OK — harness faithful' if dxy_full['trades'] in range(48, 65) else 'INVESTIGATE — anchor drift'}")

    print("\nPHASE 4 — Equity figure (full-sample, 1% risk, Scheme D)")
    fig, ax = plt.subplots(figsize=(13, 7))
    palette = {
        "DXY": "#555555", "EURUSD": "#1f77b4", "GBPUSD": "#d62728",
        "USDJPY": "#2ca02c", "USDCAD": "#9467bd", "AUDUSD": "#ff7f0e",
        "NZDUSD": "#17becf",
    }
    for sym, r in results.items():
        eq = r["full"]["equity"]
        ax.plot(eq.index, eq.values, label=f"{sym} ({r['decision']})",
                color=palette.get(sym, "#000000"),
                linewidth=1.8 if sym == "DXY" else 1.3,
                linestyle="--" if sym == "DXY" else "-")
    ax.axhline(1.0, color="black", linewidth=0.5, alpha=0.4)
    ax.set_title("H23 — Major-pair full-sample equity, daily Scheme D (DXY params, no re-tune)\n"
                 "1% risk/trade · loose-M · FLD (10,20,40) · 0/1/3 mults",
                 fontsize=11, pad=10)
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity (start = 1.0)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.95)
    plt.tight_layout()
    fig_eq = OUTDIR_FIG / "12_major_pair_equity_curves.png"
    plt.savefig(fig_eq, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  Wrote {fig_eq}")

    print("\nPHASE 5 — OOS Sortino bar chart")
    fig, ax = plt.subplots(figsize=(11, 6))
    syms = [r["symbol"] for r in order]
    vals = [0.0 if np.isnan(r["oos"]["sortino"]) else r["oos"]["sortino"]
            for r in order]
    barcolors = []
    for r in order:
        d = r["decision"]
        barcolors.append("#2ca02c" if d == "GO"
                         else "#ff7f0e" if d == "SWEEP" else "#d62728")
    bars = ax.bar(syms, vals, color=barcolors, edgecolor="black", linewidth=0.6)
    ax.axhline(3.0, color="green", linestyle="--", linewidth=1.4,
               label="GO ship-floor (Sortino = +3.0)")
    ax.axhline(1.0, color="red", linestyle=":", linewidth=1.2,
               label="NO-GO floor (Sortino = +1.0)")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + (0.08 if v >= 0 else -0.25),
                f"{v:+.2f}", ha="center", va="bottom" if v >= 0 else "top",
                fontsize=9)
    ax.set_title("H23 — OOS Sortino by symbol (last 30%, load-bearing metric)\n"
                 "green=GO  orange=SWEEP  red=NO-GO", fontsize=11, pad=10)
    ax.set_ylabel("OOS Sortino (annualized)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    fig_sortino = OUTDIR_FIG / "13_major_pair_sortino_compare.png"
    plt.savefig(fig_sortino, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  Wrote {fig_sortino}")

    serializable = {
        "seed": SEED,
        "is_fraction": IS_FRACTION,
        "scheme_d": SCHEME_D,
        "params": {"detector": "loose_M", "dip": 50.0, "fld_cycles": [10, 20, 40]},
        "yf_end": YF_END,
        "skipped": skipped,
        "symbols": {
            sym: {
                "data_first": r["data_first"], "data_last": r["data_last"],
                "data_bars": r["data_bars"],
                "is_window": r["is_window"], "oos_window": r["oos_window"],
                "full": _clean(r["full"]), "is": _clean(r["is"]),
                "oos": _clean(r["oos"]), "disloc": _clean(r["disloc"]),
                "decision": r["decision"], "decision_reason": r["decision_reason"],
            }
            for sym, r in results.items()
        },
    }
    json_path = REPO / "results" / "_h23_run.json"
    json_path.write_text(json.dumps(serializable, indent=2, default=str))
    print(f"\n  Wrote {json_path}")
    print("\nDONE.")


if __name__ == "__main__":
    main()
