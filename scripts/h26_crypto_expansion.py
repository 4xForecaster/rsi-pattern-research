#!/usr/bin/env python3
"""H26 — Crypto-major expansion of the daily M-P1 LONG framework.

FX is exhausted (M-LONG: 3 GO + 1 thin; V-SHORT: 0 GO). H26 asks whether
the *unchanged* DXY-calibrated daily Scheme D transfers to a different
asset class: crypto majors. No per-symbol tuning — same loose-M dip=50,
FLD (10,20,40), Scheme D (bull 0 / neu 1 / bear 3), 70/30 split by bars.

`run_one` is the verbatim H23/H16 engine (so DXY-anchor-faithful and
directly comparable to the FX numbers). Decision rule per the H26 brief
(note: stated on **OOS** trades, the STRICT reading — differs from H23's
full-trade-floor PRAGMATIC; followed literally here and reported both):
  GO    : OOS Sortino >= +3.0 AND OOS trades >= 30
  NO-GO : OOS Sortino <  +1.0 OR  OOS trades < 10
  SWEEP : otherwise
Thin GO (OOS trades < 20) gets the H24 4-test robustness gate.

Crypto specifics handled: yfinance "BTC-USD" style tickers; 7-day/week
bars (~365/yr vs FX ~252) so OOS windows are time-shorter per bar-count;
explicit per-symbol data-hygiene log (NaN / dup / monotonic / >50%
single-bar spike); BTC informal cycle-length recon (reconnaissance for a
possible H27 — NOT used to tune anything here).

Bonus pairs (BNB-USD, XRP-USD) are run ONLY if >=1 of BTC/ETH is GO and
no major had a data-quality problem, per the brief.
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

CACHE = REPO / "data" / "yfinance_cache"
CACHE.mkdir(parents=True, exist_ok=True)
OUTDIR_FIG = REPO / "figures"

IS_FRACTION = 0.70
SCHEME_D = (0.0, 1.0, 3.0)
SHIP_FLOOR = 3.0
PER_TRADE_FLOOR = 2.5
GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42
YF_END = "2026-05-19"
SPIKE_THRESH = 0.50  # |1-bar close-to-close| > 50% flagged (NOT removed)

MAJORS = {"BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD"}
BONUS = {"BNBUSD": "BNB-USD", "XRPUSD": "XRP-USD"}


# ---------------------------------------------------------------------------
# Data + hygiene (documented; nothing silently smoothed)
# ---------------------------------------------------------------------------

def load_crypto_cached(ticker: str) -> tuple[pd.DataFrame, dict]:
    cp = CACHE / f"{ticker.replace('=', '_').replace('^', '')}_daily.csv"
    if cp.exists():
        df = pd.read_csv(cp, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import yfinance as yf
            raw = yf.download(ticker, start="2010-01-01", end=YF_END,
                              progress=False, auto_adjust=False)
        if raw is None or raw.empty:
            raise RuntimeError(f"yfinance empty for {ticker!r}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]
        df = pd.DataFrame({
            "open": pd.to_numeric(raw["Open"], errors="coerce"),
            "high": pd.to_numeric(raw["High"], errors="coerce"),
            "low": pd.to_numeric(raw["Low"], errors="coerce"),
            "close": pd.to_numeric(raw["Close"], errors="coerce"),
            "volume": pd.to_numeric(raw.get("Volume", 0), errors="coerce"),
        })
        df.index = pd.to_datetime(raw.index, utc=True)

    n_raw = len(df)
    nan_rows = int(df[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_index()
    dups = int(df.index.duplicated().sum())
    if dups:
        df = df[~df.index.duplicated(keep="first")]
    mono = bool(df.index.is_monotonic_increasing)
    ret = df["close"].pct_change().abs()
    spike_idx = df.index[ret > SPIKE_THRESH]
    gap = df.index.to_series().diff().dt.days
    hygiene = {
        "rows_raw": n_raw,
        "rows_clean": len(df),
        "nan_rows_dropped": nan_rows,
        "dup_rows_dropped": dups,
        "monotonic": mono,
        "n_single_bar_moves_gt_50pct": int((ret > SPIKE_THRESH).sum()),
        "spike_dates": [t.date().isoformat() for t in spike_idx][:20],
        "max_day_gap": int(gap.max()) if len(gap.dropna()) else None,
        "n_day_gaps_gt_1": int((gap > 1).sum()),
        "first": df.index[0].date().isoformat(),
        "last": df.index[-1].date().isoformat(),
        "bars_per_year_est": round(len(df) / max(
            (df.index[-1] - df.index[0]).days / 365.25, 1e-9), 1),
        "data_ok": len(df) >= 250 and mono and dups == 0,
        "cleaning_applied": (
            ([f"dropped {nan_rows} NaN OHLC rows"] if nan_rows else [])
            + ([f"dropped {dups} duplicate-timestamp rows (kept first)"] if dups else [])
        ) or ["none — data clean as fetched"],
        "spikes_note": ("retained — real crypto volatility, NOT smoothed"
                        if (ret > SPIKE_THRESH).any() else "no >50% single-bar moves"),
    }
    if not cp.exists() and hygiene["data_ok"]:
        df.to_csv(cp)
    return df, hygiene


def btc_cycle_recon(df: pd.DataFrame) -> dict:
    """Informal dominant-periodicity scan on BTC 2014-2020 log returns.
    Reconnaissance for a possible H27 — NOT used to tune H26."""
    sub = df[(df.index >= pd.Timestamp("2014-01-01", tz="UTC")) &
             (df.index < pd.Timestamp("2020-01-01", tz="UTC"))]
    if len(sub) < 200:
        return {"note": "insufficient 2014-2020 BTC bars for recon"}
    lr = np.log(sub["close"]).diff().dropna().values
    lr = (lr - lr.mean()) * np.hanning(len(lr))
    ps = np.abs(np.fft.rfft(lr)) ** 2
    fr = np.fft.rfftfreq(len(lr))
    m = fr > 0
    per, pw = 1.0 / fr[m], ps[m]
    band = (per >= 4) & (per <= 160)
    top = np.argsort(pw[band])[::-1][:8]
    dom = sorted(round(float(x), 1) for x in per[band][top])
    return {
        "window": "2014-01..2019-12 BTC daily log-returns",
        "dominant_periods_bars_top8_in_4_160": dom,
        "canonical_fx_cycles": [10, 20, 40],
        "flag": ("crypto short-cycle energy (~5-8 & ~20 bars) differs from "
                 "FX 10/20/40; 40-bar parent largely absent — candidate "
                 "H27 cycle re-recon (e.g. 5/10/20 or 8/16/32). NOT tuned here."),
    }


# ---------------------------------------------------------------------------
# Engine — verbatim H23/H16 run_one
# ---------------------------------------------------------------------------

def run_one(df: pd.DataFrame, *, label: str) -> dict:
    df_rsi = indicators.add_rsi(df, period=14)
    cfg = PatternConfig(m_inner_threshold=50.0)
    trades = position_sizing.fib_long_at_p1(df_rsi, rsi_col="rsi14", cfg=cfg)
    bias = fld.fld_bias(df_rsi, cycles=(10, 20, 40))
    bull_m, neut_m, bear_m = SCHEME_D
    recs, universe = [], 0
    bias_counts = {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        universe += 1
        ets = df_rsi.index[t.entry_idx]
        lbl = bias.loc[ets, "bias_label"] if ets in bias.index else "unknown"
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        mult = bull_m if lbl == "bullish" else bear_m if lbl == "bearish" else neut_m
        if mult == 0:
            continue
        recs.append(rm.TradeRecord(entry_date=pd.Timestamp(ets),
                                   exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
                                   r_multiple=float(t.r_multiple),
                                   multiplier=float(mult)))
    eq = rm.build_equity_curve(recs, 1.0, 0.01)
    return {"label": label, "trades": len(recs), "universe": universe,
            "bias_counts": bias_counts, "sortino": float(rm.sortino(eq)),
            "sharpe": float(rm.sharpe(eq)),
            "total_R_per_year": float(rm.total_r_per_year(recs)),
            "max_dd": float(rm.max_drawdown(eq)), "equity": eq, "records": recs}


def split_70_30(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    e = int(len(df) * IS_FRACTION)
    return df.iloc[:e], df.iloc[e:]


def go_no_go(oos: dict) -> tuple[str, str]:
    """H26 brief rule — on OOS trades (STRICT)."""
    s, n = oos["sortino"], oos["trades"]
    if np.isnan(s):
        return "NO-GO", f"OOS Sortino undefined (OOS n={n})"
    if s >= SHIP_FLOOR and n >= 30:
        return "GO", f"OOS Sortino {s:+.2f}>=3.0 AND OOS trades {n}>=30"
    if s < 1.0 or n < 10:
        return "NO-GO", f"OOS Sortino {s:+.2f}<1.0 OR OOS trades {n}<10"
    return "SWEEP", f"OOS Sortino {s:+.2f} in [1,3) or OOS trades {n} in [10,30)"


# ---------------------------------------------------------------------------
# H24-style robustness (thin GO only)
# ---------------------------------------------------------------------------

def _sortino(recs: list) -> float:
    if len(recs) < 2:
        return float("nan")
    return rm.sortino(rm.build_equity_curve(recs, 1.0, 0.01))


def _gini(v: np.ndarray) -> float:
    x = np.sort(np.asarray(v, float))
    n, s = len(x), x.sum()
    if n == 0 or s == 0:
        return float("nan")
    return float((2 * np.sum(np.arange(1, n + 1) * x)) / (n * s) - (n + 1) / n)


def robustness(recs: list, oos0: pd.Timestamp, oos1: pd.Timestamp) -> dict:
    rng = np.random.RandomState(BOOT_SEED)
    np.random.seed(BOOT_SEED)
    n = len(recs)
    dist = np.empty(N_BOOT)
    for b in range(N_BOOT):
        s = _sortino([recs[i] for i in rng.randint(0, n, n)])
        dist[b] = s if np.isfinite(s) else 0.0
    p5 = float(np.percentile(dist, 5))
    span = max((oos1 - oos0).days, 1)
    win = pd.Timedelta(days=int(span * 0.5))
    wins = []
    for f in np.linspace(0.0, 0.5, 4):
        ws = oos0 + pd.Timedelta(days=int(span * f))
        wins.append(_sortino([r for r in recs if ws <= r.entry_date <= ws + win]))
    n_ge = sum(1 for w in wins if np.isfinite(w) and w >= SHIP_FLOOR)
    g = _gini(np.array([r.r_multiple * r.multiplier for r in recs]))
    drops = [_sortino([r for j, r in enumerate(recs) if j != i]) for i in range(n)]
    fd = [d for d in drops if np.isfinite(d)]
    mn = min(fd) if fd else float("nan")
    c = [p5 >= SHIP_FLOOR, n_ge >= 3,
         (not np.isnan(g)) and g <= GINI_MAX,
         (not np.isnan(mn)) and mn >= PER_TRADE_FLOOR]
    hold = sum(c)
    verdict = "SOLID_GO" if hold == 4 else "THIN_GO" if hold in (2, 3) else "DOWNGRADE_SWEEP"
    return {"boot_p5": round(p5, 3),
            "rolling": [None if not np.isfinite(w) else round(float(w), 3) for w in wins],
            "n_rolling_ge": n_ge, "gini": None if np.isnan(g) else round(g, 4),
            "per_trade_min": None if np.isnan(mn) else round(mn, 3),
            "n_hold": hold, "verdict": verdict}


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------

def evaluate(sym: str, df: pd.DataFrame) -> dict:
    np.random.seed(BOOT_SEED)
    is_df, oos_df = split_70_30(df)
    full = run_one(df, label=f"{sym} FULL")
    is_m = run_one(is_df, label=f"{sym} IS")
    oos = run_one(oos_df, label=f"{sym} OOS")
    dec, rsn = go_no_go(oos)
    rob = None
    if dec == "GO" and oos["trades"] < 20:
        rob = robustness(oos["records"], oos_df.index[0], oos_df.index[-1])
        if rob["verdict"] == "DOWNGRADE_SWEEP":
            dec, rsn = "SWEEP", rsn + f" | H24 0-1/4 -> downgraded"
        elif rob["verdict"] == "THIN_GO":
            rsn += " | H24 2-3/4 -> THIN GO (stays GO, enabled:false)"
        else:
            rsn += " | H24 4/4 -> SOLID"
    return {"symbol": sym,
            "data_first": df.index[0].date().isoformat(),
            "data_last": df.index[-1].date().isoformat(),
            "data_bars": len(df),
            "oos_window": [oos_df.index[0].date().isoformat(),
                           oos_df.index[-1].date().isoformat(), len(oos_df)],
            "is": {k: v for k, v in is_m.items() if k not in ("equity", "records")},
            "oos": {k: v for k, v in oos.items() if k not in ("equity", "records")},
            "full": {k: v for k, v in full.items() if k not in ("equity", "records")},
            "decision": dec, "reason": rsn, "robustness": rob,
            "_equity": full["equity"]}


def main() -> None:
    print("=" * 80)
    print("H26 — Crypto-major expansion (daily M-P1 LONG, DXY params, no re-tune)")
    print("=" * 80)

    data, hyg, skipped = {}, {}, {}
    for sym, tk in MAJORS.items():
        try:
            df, h = load_crypto_cached(tk)
            hyg[sym] = h
            if not h["data_ok"]:
                skipped[sym] = f"data hygiene fail: {h}"
                print(f"  [SKIP] {sym}: data hygiene fail")
                continue
            data[sym] = df
        except Exception as e:  # noqa: BLE001
            skipped[sym] = f"{tk}: {e}"
            print(f"  [SKIP] {sym}: {e}")

    print("\nDATA HYGIENE")
    for sym, h in hyg.items():
        print(f"  {sym:7s} {h['rows_clean']:>5d} bars {h['first']}->{h['last']} "
              f"~{h['bars_per_year_est']}/yr | NaN={h['nan_rows_dropped']} "
              f"dup={h['dup_rows_dropped']} mono={h['monotonic']} "
              f">50%moves={h['n_single_bar_moves_gt_50pct']} "
              f"gaps>1d={h['n_day_gaps_gt_1']} | clean={h['cleaning_applied']}")

    recon = btc_cycle_recon(data["BTCUSD"]) if "BTCUSD" in data else {"note": "BTC unavailable"}
    print(f"\nCYCLE RECON (BTC, recon only): {recon.get('dominant_periods_bars_top8_in_4_160')}")
    print(f"  flag: {recon.get('flag')}")

    print("\nPER-SYMBOL EVALUATION (70/30, OOS load-bearing, OOS-trade rule)")
    results: dict[str, dict] = {}
    for sym, df in data.items():
        r = evaluate(sym, df)
        results[sym] = r
        print(f"\n--- {sym} --- {r['data_first']}->{r['data_last']} "
              f"({r['data_bars']} bars) OOS {r['oos_window'][0]}->{r['oos_window'][1]} "
              f"({r['oos_window'][2]} bars)")
        for tag in ("is", "oos", "full"):
            m = r[tag]
            print(f"   {tag.upper():4s} trades={m['trades']:>3} (univ={m['universe']:>3}) "
                  f"Sortino={m['sortino']:>+7.2f} Sharpe={m['sharpe']:>+5.2f} "
                  f"R/yr={m['total_R_per_year']:>+6.2f} MaxDD={m['max_dd']*100:>+6.1f}%")
        if r["robustness"]:
            rb = r["robustness"]
            print(f"   H24 robustness: {rb['verdict']} ({rb['n_hold']}/4) "
                  f"boot_p5={rb['boot_p5']} roll={rb['rolling']}({rb['n_rolling_ge']}/4) "
                  f"gini={rb['gini']} per_trade_min={rb['per_trade_min']}")
        print(f"   ==> {r['decision']}  ({r['reason']})")

    # Bonus pairs only if >=1 of BTC/ETH GO and no major data problem
    majors_ok = all(hyg.get(s, {}).get("data_ok") for s in MAJORS if s in hyg) and not skipped
    btc_eth_go = any(results.get(s, {}).get("decision") == "GO" for s in ("BTCUSD", "ETHUSD"))
    if btc_eth_go and majors_ok:
        print("\nBONUS PAIRS (>=1 of BTC/ETH GO and majors clean) — running BNB/XRP")
        for sym, tk in BONUS.items():
            try:
                df, h = load_crypto_cached(tk)
                hyg[sym] = h
                if not h["data_ok"]:
                    skipped[sym] = "data hygiene fail"
                    continue
                r = evaluate(sym, df)
                results[sym] = r
                print(f"  {sym}: {r['decision']} OOS S={r['oos']['sortino']:+.2f} "
                      f"n={r['oos']['trades']}/{r['full']['trades']}")
            except Exception as e:  # noqa: BLE001
                skipped[sym] = str(e)
    else:
        print(f"\nBONUS PAIRS SKIPPED per rule (BTC/ETH GO={btc_eth_go}, "
              f"majors_ok={majors_ok}).")

    # FX reference (M-LONG OOS Sortino) from _h23_run.json
    fx_ref = {}
    try:
        h23 = json.loads((REPO / "results" / "_h23_run.json").read_text())
        fx_ref = {s: {"oos_sortino": v["oos"]["sortino"],
                      "decision": v["decision"]}
                  for s, v in h23["symbols"].items()}
    except Exception:  # noqa: BLE001
        pass

    # ---- Figure 18: crypto equity curves ----
    fig, ax = plt.subplots(figsize=(13, 7))
    pal = {"BTCUSD": "#f7931a", "ETHUSD": "#627eea", "SOLUSD": "#14f195",
           "BNBUSD": "#f3ba2f", "XRPUSD": "#23292f"}
    for sym, r in results.items():
        eq = r["_equity"]
        ax.plot(eq.index, eq.values, label=f"{sym} ({r['decision']})",
                color=pal.get(sym, "#000"), linewidth=1.5)
    ax.axhline(1.0, color="black", linewidth=0.5, alpha=0.4)
    ax.set_title("H26 — Crypto full-sample equity, daily M-P1 LONG Scheme D "
                 "(DXY params, no re-tune)\n1% risk · loose-M · FLD (10,20,40) · "
                 "0/1/3 mults", fontsize=11, pad=10)
    ax.set_xlabel("Date"); ax.set_ylabel("Equity (start = 1.0)")
    ax.grid(True, alpha=0.3); ax.legend(loc="upper left", fontsize=9)
    plt.tight_layout()
    f18 = OUTDIR_FIG / "18_crypto_equity_curves.png"
    plt.savefig(f18, dpi=140, bbox_inches="tight"); plt.close()
    print(f"\nWrote {f18}")

    # ---- Figure 19: crypto vs FX OOS Sortino (categorical scatter) ----
    fig, ax = plt.subplots(figsize=(11, 6.5))
    rng = np.random.RandomState(1)

    def clip(v): return max(-3.0, min(9.0, v)) if np.isfinite(v) else -3.0
    for s, v in fx_ref.items():
        x = 0 + rng.uniform(-0.18, 0.18)
        ax.scatter(x, clip(v["oos_sortino"]), s=80, color="#1f77b4",
                   edgecolor="black", linewidth=0.5, zorder=3)
        ax.annotate(s, (x, clip(v["oos_sortino"])), textcoords="offset points",
                    xytext=(6, 3), fontsize=8)
    for s, r in results.items():
        x = 1 + rng.uniform(-0.18, 0.18)
        ax.scatter(x, clip(r["oos"]["sortino"]), s=110, color="#ff7f0e",
                   edgecolor="black", linewidth=0.6, zorder=3, marker="D")
        ax.annotate(f"{s}\n({r['decision']})", (x, clip(r["oos"]["sortino"])),
                    textcoords="offset points", xytext=(7, 3), fontsize=8.5,
                    fontweight="bold")
    ax.axhline(SHIP_FLOOR, color="green", ls="--", lw=1.4, label="GO floor +3.0")
    ax.axhline(1.0, color="red", ls=":", lw=1.2, label="NO-GO floor +1.0")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["FX (M-LONG, H23)", "Crypto (H26)"])
    ax.set_xlim(-0.5, 1.6); ax.set_ylim(-3.2, 9.3)
    ax.set_ylabel("OOS Sortino (clipped [-3, 9])")
    ax.set_title("H26 — OOS Sortino: crypto majors vs FX (M-LONG)\n"
                 "blue=FX  orange♦=crypto", fontsize=11, pad=10)
    ax.grid(True, axis="y", alpha=0.3); ax.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    f19 = OUTDIR_FIG / "19_crypto_vs_fx_sortino.png"
    plt.savefig(f19, dpi=140, bbox_inches="tight"); plt.close()
    print(f"Wrote {f19}")

    dump = {"seed": BOOT_SEED, "is_fraction": IS_FRACTION,
            "scheme_d": SCHEME_D, "decision_rule": "OOS-trade STRICT (H26 brief)",
            "cycle_recon": recon, "hygiene": hyg, "skipped": skipped,
            "fx_reference": fx_ref,
            "pairs": {s: {k: v for k, v in r.items() if k != "_equity"}
                      for s, r in results.items()}}
    (REPO / "results" / "_h26_run.json").write_text(json.dumps(dump, indent=2, default=str))
    n_go = sum(1 for r in results.values() if r["decision"] == "GO")
    print(f"\nWrote {REPO/'results'/'_h26_run.json'}")
    print(f"CRYPTO GO count: {n_go} -> "
          f"{'wire hurst-agent integration' if n_go else 'NEGATIVE RESULT, no integration'}")
    print("DONE.")


if __name__ == "__main__":
    main()
