#!/usr/bin/env python3
"""H21 — Short-side V-pattern variant, first-pass backtest.

Does the symmetric SHORT mirror of the M-P1 LONG strategy produce ANY
positive edge? If yes, follow-up commits add walk-forward + cross-symbol
+ hurst-agent wiring. If no, document the null and move on.

Setup mirrors H14 5m DXY exactly except:
- Detector: strict_V instead of strict_M (symmetric thresholds 70/28/28
  vs M's 30/72/72)
- Entry: T1+1 of V instead of P1+1 of M
- Direction: SHORT instead of LONG
- FLD bias roles swap: BULLISH FLD bias (price overextended above all
  FLDs) is the high-conviction setup for shorts (mirror of bearish for
  longs)
- Scheme G mirror: bullish_intraday_fld → 5×, neutral → 1×, bearish → 1×
- range/stop/targets all mirrored vertically by ``fib_short_at_v_t1``

Runs the 5-scheme sweep (A/B/C/D/E with multipliers re-keyed for
shorts: bullish/neutral/bearish remains the column header, but the
"big payoff" column is bullish now), reports the full metric stack,
and applies the H14 production-decision rule.

NO walk-forward in this script — scope is "does the edge exist at all?"
If yes, H22 does walk-forward; if no, document and stop.
"""
from __future__ import annotations
import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import data as data_mod
from rsi_pattern import indicators, fld
from rsi_pattern import intraday as itd
from rsi_pattern import position_sizing as ps
from rsi_pattern.patterns_strict_v import StrictVConfig
from rsi_pattern import risk_metrics as rm


TF = "5m"
PERIODS_PER_YEAR_5M = 252 * 288

# Scheme labels — for SHORTS the "big payoff" bucket is BULLISH FLD bias
# (price overextended above all FLDs = high conviction for mean reversion
# down). Multipliers tuple is (bullish_fld, neutral_fld, bearish_fld).
SCHEMES_SHORT = {
    "A. Pure parallel (1/1/1)":      (1.0, 1.0, 1.0),
    "B. Modest (3/1/1)":             (3.0, 1.0, 1.0),
    "C. Aggressive (5/1/1)":         (5.0, 1.0, 1.0),
    "D. Skip bearish + 3x bullish":  (3.0, 1.0, 0.0),
    "E. Conservative (3/1/0.5)":     (3.0, 1.0, 0.5),
}


def load_5m() -> pd.DataFrame:
    data_mod.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
    return data_mod.load_dxy(TF)


def run_scheme(df: pd.DataFrame, scheme_mults: tuple) -> dict:
    df_rsi = indicators.add_rsi(df, period=14)
    bias = fld.fld_bias(df_rsi, cycles=itd.INTRADAY_FLD_CYCLES[TF])

    # Symmetric V-side strict thresholds derived from H14 long-side 30/72/72
    vcfg = StrictVConfig(
        fall_origin_above=70.0,        # 100 - 30
        major_trough_max=28.0,         # 100 - 72
        wiggle_peak_ceiling=28.0,      # 100 - 72
        completion_threshold=50.0,
    )
    fib_trades = ps.fib_short_at_v_t1(
        df_rsi, rsi_col="rsi14", v_cfg=vcfg,
        max_bars=itd.INTRADAY_TIME_STOP_BARS[TF],
        lookback_bars=itd.INTRADAY_FLD_CYCLES[TF][-1],
    )

    bull_m, neut_m, bear_m = scheme_mults
    mults, bias_counts = [], {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    for t in fib_trades:
        if t.exit_idx is None or t.r_multiple is None:
            mults.append(0.0)
            continue
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        if lbl == "bullish":   mults.append(bull_m)
        elif lbl == "bearish": mults.append(bear_m)
        else:                  mults.append(neut_m)

    r_records = []
    for t, m in zip(fib_trades, mults):
        if t.exit_idx is None or t.r_multiple is None or m == 0:
            continue
        r_records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(df_rsi.index[t.entry_idx]),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(m),
        ))
    mtm = itd.fib_to_mtm(fib_trades, df_rsi, mults, spread=itd.INTRADAY_SPREAD[TF])
    equity = rm.build_equity_curve_mtm(
        mtm, df_rsi["close"], initial_capital=1.0, risk_per_trade=0.01,
    )
    return {
        "trades": len(r_records),
        "universe": sum(1 for t in fib_trades if t.r_multiple is not None),
        "bias_counts": bias_counts,
        "mean_R_weighted": (float(np.mean([r.r_multiple * r.multiplier for r in r_records]))
                            if r_records else float("nan")),
        "total_R_per_year": rm.total_r_per_year(r_records),
        "sharpe": rm.sharpe(equity, periods_per_year=PERIODS_PER_YEAR_5M),
        "sortino": rm.sortino(equity, periods_per_year=PERIODS_PER_YEAR_5M),
        "max_dd": rm.max_drawdown(equity),
    }


def fmt(m: dict) -> str:
    return (f"trades={m['trades']:>3d} meanR={m['mean_R_weighted']:>+5.2f} "
            f"R/yr={m['total_R_per_year']:>+6.2f} "
            f"Sharpe={m['sharpe']:>+5.2f} Sortino={m['sortino']:>+5.2f} "
            f"MaxDD={m['max_dd']*100:>+6.2f}%")


def main():
    df = load_5m()
    print("=" * 84)
    print("H21 — Short-side V-pattern first-pass backtest (5m DXY, full window)")
    print("=" * 84)
    print(f"5m bars: {len(df)}, {df.index[0]} → {df.index[-1]}")
    print(f"Strict-V thresholds (mirror of H14 30/72/72): "
          f"fall_origin_above=70, major_trough_max=28, wiggle_peak_ceiling=28")
    print(f"FLD cycles: {itd.INTRADAY_FLD_CYCLES[TF]}  "
          f"lookback={itd.INTRADAY_FLD_CYCLES[TF][-1]}  "
          f"time_stop={itd.INTRADAY_TIME_STOP_BARS[TF]}  "
          f"spread={itd.INTRADAY_SPREAD[TF]*1e4:.1f}bps")
    print()

    results = {}
    for name, mults in SCHEMES_SHORT.items():
        m = run_scheme(df, mults)
        results[name] = m
        print(f"  {name:<32} {fmt(m)}")
        print(f"    bias: {m['bias_counts']}")

    # Honest read
    print()
    print("=" * 84)
    base = results["A. Pure parallel (1/1/1)"]
    has_signal = (base["trades"] >= 10
                  and not np.isnan(base["sortino"])
                  and base["sortino"] > 0.5)
    if not has_signal:
        print("VERDICT: NULL — short side does not produce a usable edge on this window.")
        print("  Scheme A (no scaling) is the cleanest read of raw setup quality.")
        print(f"  trades={base['trades']}, Sortino={base['sortino']:+.2f}, "
              f"MeanR={base['mean_R_weighted']:+.2f}")
        print("  Recommendation: do NOT proceed to walk-forward / cross-symbol. "
              "Mirror approach does not transfer.")
    else:
        # Pick best scheme by Sortino
        valid = [(n, m) for n, m in results.items()
                 if m["trades"] >= 10 and not np.isnan(m["sortino"])]
        valid.sort(key=lambda x: -x[1]["sortino"])
        winner_name, winner = valid[0]
        print(f"VERDICT: SIGNAL — short side has a positive edge.")
        print(f"  Best scheme: {winner_name}")
        print(f"    {fmt(winner)}")
        print(f"  Baseline (Scheme A): {fmt(base)}")
        print()
        # Production decision (same gates as H20)
        s, n, dd = winner["sortino"], winner["trades"], winner["max_dd"]
        if s >= 2.5 and n >= 30 and dd > -0.15:
            decision = "PROMISING — schedule H22 walk-forward + cross-symbol"
        elif s >= 1.0:
            decision = "MARGINAL — promising signal but below production gates; document"
        else:
            decision = "WEAK — positive but below useful threshold"
        print(f"  Production gate: Sortino≥2.5 AND trades≥30 AND DD>-15%")
        print(f"  Decision: {decision}")
    print("=" * 84)

    # Dump
    out_path = REPO / "results" / "_h21_run.json"
    def _scrub(d):
        return {k: (None if isinstance(v, float) and np.isnan(v) else v)
                for k, v in d.items()}
    out_path.write_text(json.dumps({
        "timeframe": TF,
        "data_window": [str(df.index[0]), str(df.index[-1]), len(df)],
        "v_thresholds": {"fall_origin_above": 70.0, "major_trough_max": 28.0,
                         "wiggle_peak_ceiling": 28.0},
        "fld_cycles": list(itd.INTRADAY_FLD_CYCLES[TF]),
        "schemes_short": {name: list(mults) for name, mults in SCHEMES_SHORT.items()},
        "results": {name: _scrub(m) for name, m in results.items()},
        "has_signal": has_signal,
    }, indent=2, default=str))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
