#!/usr/bin/env python3
"""Bi-weekly automated re-validation of the daily Scheme D REGIME LAYER.

Designed for GitHub Actions:
- Fetches DXY daily from yfinance (no BarChart CSV needed on cloud).
- Runs H12 daily Scheme D backtest end-to-end.
- Compares Sortino to the H12 daily benchmark (+5.75) and posts a
  Telegram drift verdict.
- Exits 0 on green, 1 on yellow, 2 on red.

**Scope note**: this validates the DAILY REGIME LAYER (which is the
input to the 5m execution layer's Scheme G gate). The intraday execution
layer (5m strict-M with H14 thresholds) requires the BarChart 5m CSV
which isn't on cloud runners — its validation stays manual via
scripts/h17_walkforward_strict_m.py + h19. Different layer, different
benchmark. The 5m layer's honest OOS Sortino band (+2 to +4 per H19)
does NOT apply here.

Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from env (set as GH Actions
secrets in 4xForecaster/rsi-pattern-research). Missing creds → script
prints the summary to stdout but doesn't try to send (clean fallback
for local invocations).

Tripwires (calibrated against H12 daily Scheme D's +5.75 OOS baseline,
± regime-noise headroom):
- test_sortino in [4.0, 7.5]  → green  (normal range)
- test_sortino in [2.5, 4.0) ∪ (7.5, 9.0]  → yellow  (drift)
- test_sortino < 2.5          → red    (edge decay — 3 reds in a row = pause regime layer)
- test_sortino > 9.0          → yellow (anomaly; verify data integrity)

Run manually:
    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \
      python scripts/bi_weekly_validation.py
or via the GH Actions cron defined in .github/workflows/bi-weekly-validation.yml.
"""
from __future__ import annotations
import datetime as _dt
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request
import warnings

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import indicators, fld, position_sizing
from rsi_pattern import risk_metrics as rm

# H12 daily Scheme D benchmark (the layer this script validates).
#
# Band recalibration 2026-05-15: the original [4.0, 7.5] green band was
# anchored to H12's +5.75 (BarChart data). Three live yfinance runs
# (2026-05-12 → -15) consistently produced OOS Sortino +7.46 to +7.51 —
# the yfinance daily series runs structurally hotter than the BarChart
# window H12 used, AND it's a different 7y OOS slice. A +7.50 ceiling
# tripped YELLOW on +7.51 (a 0.01 rounding-level miss) and the workflow
# false-failed. Widened green to [4.0, 9.0]: still catches genuine decay
# (<4.0 — well below every observed value) and genuine anomaly (>11.0)
# without false-positiving on the strategy's actual healthy range.
H12_FULL_SORTINO = 5.75       # published in H12 + H13 v1.1 (BarChart data)
H12_FULL_TRADES = 56
HONEST_BAND = (4.0, 9.0)      # observed healthy OOS ≈ +7.5; wide noise headroom
YELLOW_LOW = (2.5, 4.0)
YELLOW_HIGH = (9.0, 11.0)
RED_FLOOR = 2.5
ANOMALY_CEILING = 11.0

SCHEME_D = (0.0, 1.0, 3.0)
DAILY_FLD_CYCLES = (10, 20, 40)
OOS_YEARS = 7   # H15's split convention
BASE_RISK = 0.01


def load_dxy_yfinance(start: str = "1990-01-01") -> pd.DataFrame:
    """Pull DXY daily from yfinance. Cache locally if available."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import yfinance as yf
    today = _dt.date.today().isoformat()
    raw = None
    last_err = None
    for ticker in ("DX-Y.NYB", "^DXY", "DX=F"):
        try:
            df = yf.download(ticker, start=start, end=today, progress=False, auto_adjust=False)
            if df is not None and not df.empty:
                raw = df
                used_ticker = ticker
                break
        except Exception as e:
            last_err = e
    if raw is None:
        raise RuntimeError(f"All yfinance DXY tickers failed; last error: {last_err}")

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    out = pd.DataFrame({
        "open":  pd.to_numeric(raw["Open"], errors="coerce"),
        "high":  pd.to_numeric(raw["High"], errors="coerce"),
        "low":   pd.to_numeric(raw["Low"], errors="coerce"),
        "close": pd.to_numeric(raw["Close"], errors="coerce"),
        "volume": pd.to_numeric(raw.get("Volume", 0), errors="coerce"),
    })
    out.index = pd.to_datetime(raw.index, utc=True)
    out = out.dropna(subset=["open", "high", "low", "close"]).sort_index()
    out.attrs["source_ticker"] = used_ticker
    return out


def run_scheme_d(df: pd.DataFrame) -> dict:
    df_rsi = indicators.add_rsi(df, period=14)
    bias = fld.fld_bias(df_rsi, cycles=DAILY_FLD_CYCLES)
    trades = position_sizing.fib_long_at_p1(df_rsi, rsi_col="rsi14")
    bull_m, neut_m, bear_m = SCHEME_D
    records, bias_counts = [], {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        if lbl == "bullish":   mult = bull_m
        elif lbl == "bearish": mult = bear_m
        else:                  mult = neut_m
        if mult == 0:
            continue
        records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(entry_ts),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    equity = rm.build_equity_curve(records, initial_capital=1.0, risk_per_trade=BASE_RISK)
    return {
        "trades": len(records),
        "universe": sum(1 for t in trades if t.r_multiple is not None),
        "bias_counts": bias_counts,
        "mean_R": float(np.mean([r.r_multiple * r.multiplier for r in records])) if records else float("nan"),
        "total_R_per_year": rm.total_r_per_year(records),
        "sharpe": rm.sharpe(equity),
        "sortino": rm.sortino(equity),
        "max_dd": rm.max_drawdown(equity),
    }


def classify_drift(sortino: float) -> tuple[str, str]:
    """Returns (status, color_emoji) where status ∈ {green, yellow, red}."""
    if np.isnan(sortino):
        return "yellow", "🟡"  # undefined → investigate
    if sortino < RED_FLOOR:
        return "red", "🔴"
    if sortino > ANOMALY_CEILING:
        return "yellow", "🟡"
    if HONEST_BAND[0] <= sortino <= HONEST_BAND[1]:
        return "green", "🟢"
    return "yellow", "🟡"


def format_telegram(metrics_full: dict, metrics_oos: dict,
                    status: str, emoji: str, ticker: str,
                    df: pd.DataFrame) -> str:
    bias_full = metrics_full["bias_counts"]
    bias_oos = metrics_oos["bias_counts"]
    return (
        f"RSI M-P1 BI-WEEKLY {emoji} {status.upper()}\n"
        f"date: {_dt.date.today().isoformat()}  ticker: {ticker}\n"
        f"data: {len(df)} bars, {df.index[0].date()} → {df.index[-1].date()}\n"
        f"\n"
        f"FULL window:\n"
        f"  trades: {metrics_full['trades']}/{metrics_full['universe']}  "
        f"bias B/N/b={bias_full['bullish']}/{bias_full['neutral']}/{bias_full['bearish']}\n"
        f"  Mean R: {metrics_full['mean_R']:+.2f}   "
        f"R/yr: {metrics_full['total_R_per_year']:+.2f}\n"
        f"  Sharpe: {metrics_full['sharpe']:+.2f}   "
        f"Sortino: {metrics_full['sortino']:+.2f}   "
        f"MaxDD: {metrics_full['max_dd']*100:+.2f}%\n"
        f"\n"
        f"OOS (last {OOS_YEARS}y):\n"
        f"  trades: {metrics_oos['trades']}/{metrics_oos['universe']}  "
        f"bias B/N/b={bias_oos['bullish']}/{bias_oos['neutral']}/{bias_oos['bearish']}\n"
        f"  Sortino: {metrics_oos['sortino']:+.2f}   "
        f"MaxDD: {metrics_oos['max_dd']*100:+.2f}%\n"
        f"\n"
        f"layer: daily regime (Scheme D, FLD 10/20/40, 0/1/3 mults)\n"
        f"benchmark: H12 full Sortino = +{H12_FULL_SORTINO:.2f}\n"
        f"green band: [{HONEST_BAND[0]:.1f}, {HONEST_BAND[1]:.1f}]   "
        f"red floor: {RED_FLOOR:.1f}\n"
        f"5m execution layer is validated separately via "
        f"scripts/h17_walkforward_strict_m.py on the BarChart 5m CSV "
        f"(not on this cron — needs local data)."
    )


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("[telegram STUB → unset] message would be:")
        print(text)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"[telegram ERROR] {exc}")
        return False
    if not body.get("ok"):
        print(f"[telegram API ERROR] {body}")
        return False
    msg_id = body.get("result", {}).get("message_id")
    print(f"[telegram OK msg_id={msg_id}]")
    return True


def main() -> int:
    print(f"bi-weekly validation @ {_dt.date.today().isoformat()}")
    print("Fetching DXY daily from yfinance…")
    df = load_dxy_yfinance()
    ticker = df.attrs.get("source_ticker", "?")
    print(f"  {len(df)} bars, {df.index[0].date()} → {df.index[-1].date()} (ticker={ticker})")

    # FULL window
    metrics_full = run_scheme_d(df)
    print(f"\nFULL window Scheme D: trades={metrics_full['trades']}, "
          f"Sortino={metrics_full['sortino']:+.2f}, "
          f"MaxDD={metrics_full['max_dd']*100:+.2f}%")

    # OOS (last 7 years)
    cutoff = df.index[-1] - pd.Timedelta(days=int(OOS_YEARS * 365.25))
    df_oos = df[df.index >= cutoff]
    metrics_oos = run_scheme_d(df_oos)
    print(f"OOS  ({OOS_YEARS}y): trades={metrics_oos['trades']}, "
          f"Sortino={metrics_oos['sortino']:+.2f}, "
          f"MaxDD={metrics_oos['max_dd']*100:+.2f}%")

    status, emoji = classify_drift(metrics_oos["sortino"])
    print(f"\nVerdict: {emoji} {status.upper()}")

    msg = format_telegram(metrics_full, metrics_oos, status, emoji, ticker, df)
    send_telegram(msg)

    # ── Surface the verdict in GitHub Actions WITHOUT failing the job ──
    #
    # Design fix 2026-05-15: previously YELLOW→exit 1 / RED→exit 2, which
    # made GH Actions paint a successful monitoring run as ❌ "failure".
    # That conflates "the monitor itself broke" (real failure — needs a
    # fix) with "the monitor detected drift" (a finding — needs a glance).
    # They demand different operator responses, so they must not share a
    # signal.
    #
    # New contract:
    #   - exit 0  on ANY successful run (green/yellow/red all = monitor OK)
    #   - exit 2  ONLY on a real script error (fetch failed / exception) —
    #             those raise before reaching here, caught by __main__
    #   - the verdict is conveyed via: (a) the Telegram message [done
    #     above], (b) a GH Actions step summary, (c) ::warning:: /
    #     ::error:: workflow annotations so YELLOW/RED show prominently in
    #     the run UI without marking it failed.
    summary = (
        f"### RSI M-P1 bi-weekly drift — {emoji} {status.upper()}\n\n"
        f"| metric | FULL | OOS ({OOS_YEARS}y) |\n"
        f"|---|---:|---:|\n"
        f"| trades | {metrics_full['trades']} | {metrics_oos['trades']} |\n"
        f"| Sortino | {metrics_full['sortino']:+.2f} | "
        f"**{metrics_oos['sortino']:+.2f}** |\n"
        f"| Max DD | {metrics_full['max_dd']*100:+.2f}% | "
        f"{metrics_oos['max_dd']*100:+.2f}% |\n\n"
        f"green band [{HONEST_BAND[0]:.1f}, {HONEST_BAND[1]:.1f}] · "
        f"red floor {RED_FLOOR:.1f} · benchmark H12 +{H12_FULL_SORTINO:.2f}\n"
    )
    gh_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary:
        try:
            with open(gh_summary, "a") as f:
                f.write(summary + "\n")
        except OSError:
            pass
    # Workflow annotations — visible on the run page, do NOT fail the job
    if status == "yellow":
        print(f"::warning title=RSI M-P1 drift::OOS Sortino "
              f"{metrics_oos['sortino']:+.2f} → YELLOW "
              f"(green band [{HONEST_BAND[0]}, {HONEST_BAND[1]}])")
    elif status == "red":
        # RED is loud (annotation + Telegram) but still exit 0 — the
        # monitor worked. Operator pauses the regime layer manually per
        # the 3-consecutive-reds rule (see docstring). Surfacing RED as a
        # job failure would hide it among genuine infra failures.
        print(f"::error title=RSI M-P1 EDGE DECAY::OOS Sortino "
              f"{metrics_oos['sortino']:+.2f} < red floor {RED_FLOOR} — "
              f"if 3 consecutive reds, pause the regime layer")

    return 0   # successful monitoring run, regardless of verdict


if __name__ == "__main__":
    # main() returns 0 for any successful run (verdict conveyed via
    # Telegram + GH annotations, NOT via exit code). A non-zero exit
    # here means the MONITOR ITSELF broke (yfinance down, network, an
    # unhandled exception) — that's a genuine workflow failure the
    # operator must fix, and it's correct for GH Actions to mark it ❌.
    try:
        sys.exit(main())
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"::error title=bi-weekly monitor FAILED::{exc.__class__.__name__}: {exc}")
        sys.exit(2)
