#!/usr/bin/env python3
"""H30 — Box-pattern backtest with the CORRECTED spec (T1/2 endpoint = P2,
strict confirmation gate, max-length cap, two target variants).

H29 had two material errors flagged by Dr. A and fixed in
``src/rsi_pattern/box_pattern.py``: (i) T-mid was (P0+P3)/2 — contaminated
by the breakout phase — now (P0+P2)/2 by default; (ii) the detector had no
max-length cap, producing a 1024-bar mega-box; now capped at 250 bars.

H30 also tests two target ladders side-by-side:
  VARIANT A (Dr. A's primary): 1.618 / 2.345 / 3.456 × height, projected
    from the end of P2 in the breakout direction.
  VARIANT B (alternative):     1.618 / 2.236 / 3.618 × height, projected
    from P1 in the breakout direction.

Same H12 metric stack, same 70/30 split, same locked rule:
  GO    OOS Sortino ≥ +3.0 AND OOS trades ≥ 30
  NO-GO OOS Sortino <  +1.0 OR  OOS trades < 10
  SWEEP otherwise
Thin GO (OOS trades < 20) → H24 4-test robustness gate.

H29 results live on disk (results/H29_box_pattern_validation.md +
_h29_run.json) and are loaded here for the side-by-side delta table.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import box_pattern as bp
from rsi_pattern import risk_metrics as rm

CACHE = REPO / "data" / "yfinance_cache"
IS_FRACTION = 0.70
SHIP_FLOOR = 3.0
PER_TRADE_FLOOR = 2.5
GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42
THIN_OOS = 20

YF = {"EURUSD": "EURUSD_X", "GBPUSD": "GBPUSD_X", "USDJPY": "USDJPY_X",
      "USDCAD": "USDCAD_X", "AUDUSD": "AUDUSD_X", "NZDUSD": "NZDUSD_X"}
ORDER = ["DXY", "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "NZDUSD"]


def load(sym: str) -> pd.DataFrame:
    if sym == "DXY":
        from rsi_pattern import data as dm
        dm.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
        return dm.load_dxy("daily")
    df = pd.read_csv(CACHE / f"{YF[sym]}_daily.csv", index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def split_70_30(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    e = int(len(df) * IS_FRACTION)
    return df.iloc[:e], df.iloc[e:]


def box_records(df: pd.DataFrame, direction: str, variant: str
                ) -> tuple[list[rm.TradeRecord], int, int]:
    boxes = bp.detect_boxes_df(df, direction=direction)
    universe = len(boxes); aligned = 0
    recs: list[rm.TradeRecord] = []
    for box in boxes:
        if not box.trade_aligned:
            continue
        aligned += 1
        trade = bp.box_to_trade(box, df, bias_filter=True, target_variant=variant)
        if trade is None or trade.exit_idx is None or trade.r_multiple is None:
            continue
        recs.append(rm.TradeRecord(
            entry_date=pd.Timestamp(df.index[trade.entry_idx]),
            exit_date=pd.Timestamp(df.index[trade.exit_idx]),
            r_multiple=float(trade.r_multiple), multiplier=1.0,
        ))
    return recs, universe, aligned


def metrics(records: list[rm.TradeRecord]) -> dict:
    eq = rm.build_equity_curve(records, 1.0, 0.01)
    return {"trades": len(records), "sortino": float(rm.sortino(eq)),
            "sharpe": float(rm.sharpe(eq)), "max_dd": float(rm.max_drawdown(eq)),
            "total_R_per_year": float(rm.total_r_per_year(records)),
            "_records": records, "_equity": eq}


def go_no_go(oos: dict) -> tuple[str, str]:
    s, n = oos["sortino"], oos["trades"]
    if np.isnan(s):
        return "NO-GO", f"OOS Sortino undefined (n={n})"
    if s >= SHIP_FLOOR and n >= 30:
        return "GO", f"OOS Sortino {s:+.2f}≥3 AND OOS trades {n}≥30"
    if s < 1.0 or n < 10:
        return "NO-GO", f"OOS Sortino {s:+.2f}<1 OR OOS trades {n}<10"
    return "SWEEP", f"OOS Sortino {s:+.2f} in [1,3) or trades {n} in [10,30)"


# H24 robustness (lightweight) — only invoked for clearing pairs
def _sortino(recs):
    if len(recs) < 2:
        return float("nan")
    return rm.sortino(rm.build_equity_curve(recs, 1.0, 0.01))


def _gini(v):
    x = np.sort(np.asarray(v, float)); n, s = len(x), x.sum()
    if n == 0 or s == 0:
        return float("nan")
    return float((2 * np.sum(np.arange(1, n + 1) * x)) / (n * s) - (n + 1) / n)


def robustness(recs, oos0, oos1):
    rng = np.random.RandomState(BOOT_SEED); np.random.seed(BOOT_SEED)
    n = len(recs); dist = np.empty(N_BOOT)
    for b in range(N_BOOT):
        s = _sortino([recs[i] for i in rng.randint(0, n, n)])
        dist[b] = s if np.isfinite(s) else 0.0
    p5 = float(np.percentile(dist, 5))
    span = max((oos1 - oos0).days, 1); win = pd.Timedelta(days=int(span * 0.5))
    wins = []
    for f in np.linspace(0.0, 0.5, 4):
        ws = oos0 + pd.Timedelta(days=int(span * f))
        wins.append(_sortino([r for r in recs if ws <= r.entry_date <= ws + win]))
    n_ge = sum(1 for w in wins if np.isfinite(w) and w >= SHIP_FLOOR)
    g = _gini(np.array([r.r_multiple for r in recs]))
    drops = [_sortino([r for j, r in enumerate(recs) if j != i]) for i in range(n)]
    fd = [d for d in drops if np.isfinite(d)]; mn = min(fd) if fd else float("nan")
    c = [p5 >= SHIP_FLOOR, n_ge >= 3,
         (not np.isnan(g)) and g <= GINI_MAX,
         (not np.isnan(mn)) and mn >= PER_TRADE_FLOOR]
    hold = sum(c)
    return {"boot_p5": round(p5, 3), "n_rolling_ge": n_ge,
            "gini": None if np.isnan(g) else round(g, 4),
            "per_trade_min": None if np.isnan(mn) else round(mn, 3),
            "n_hold": hold,
            "verdict": "SOLID_GO" if hold == 4 else "THIN_GO" if hold in (2, 3) else "DOWNGRADE_SWEEP"}


def evaluate_pair(sym: str, df: pd.DataFrame, variant: str) -> dict:
    np.random.seed(BOOT_SEED)
    is_df, oos_df = split_70_30(df)
    f_recs, f_univ, f_align = box_records(df, "long", variant)
    o_recs, o_univ, o_align = box_records(oos_df, "long", variant)
    Mf = metrics(f_recs); Mo = metrics(o_recs)
    dec, rsn = go_no_go(Mo)
    rob = None
    if dec == "GO" and Mo["trades"] < THIN_OOS:
        rob = robustness(Mo["_records"], oos_df.index[0], oos_df.index[-1])
        if rob["verdict"] == "DOWNGRADE_SWEEP":
            dec, rsn = "SWEEP", rsn + " | H24 0-1/4 → downgraded"
        elif rob["verdict"] == "THIN_GO":
            rsn += " | H24 2-3/4 → THIN GO"
    return {"oos_window": [oos_df.index[0].date().isoformat(),
                           oos_df.index[-1].date().isoformat(), len(oos_df)],
            "universe_full": f_univ, "aligned_full": f_align,
            "trades_full": Mf["trades"], "sortino_full": round(Mf["sortino"], 3),
            "max_dd_full": round(Mf["max_dd"], 4),
            "universe_oos": o_univ, "aligned_oos": o_align,
            "trades_oos": Mo["trades"], "sortino_oos": round(Mo["sortino"], 3),
            "max_dd_oos": round(Mo["max_dd"], 4),
            "decision": dec, "reason": rsn, "robustness": rob}


def load_h29_results() -> dict:
    try:
        with open(REPO / "results" / "_h29_run.json") as f:
            return json.load(f).get("results", {})
    except Exception:  # noqa: BLE001
        return {}


def main() -> None:
    print("=" * 82)
    print("H30 — Box pattern with CORRECTED spec (T1/2=(P0+P2)/2, max_length=250)")
    print(f"     defaults: t_endpoint=p2  max_length={bp.MAX_LENGTH_BARS}")
    print("=" * 82)
    data = {sym: load(sym) for sym in ORDER}

    # Detector-level sanity vs H29 — how many fewer boxes after max-length cap?
    print("\nDETECTOR SANITY")
    for sym in ORDER:
        df = data[sym]
        n_corr_long  = len(bp.detect_boxes_df(df, "long"))                  # H30 default
        n_corr_short = len(bp.detect_boxes_df(df, "short"))
        n_h29_long   = len(bp.detect_boxes_df(df, "long",  t_endpoint="p3", max_length=None))
        n_h29_short  = len(bp.detect_boxes_df(df, "short", t_endpoint="p3", max_length=None))
        print(f"  {sym:7s} long: H29 {n_h29_long:>3d} → H30 {n_corr_long:>3d} | "
              f"short: H29 {n_h29_short:>3d} → H30 {n_corr_short:>3d}")

    h29 = load_h29_results()
    results = {"A": {}, "B": {}}
    print("\nPER-PAIR EVALUATION (70/30; LONG boxes; both target variants)")
    for sym in ORDER:
        for variant in ("A", "B"):
            r = evaluate_pair(sym, data[sym], variant)
            results[variant][sym] = r
        ra = results["A"][sym]; rb = results["B"][sym]
        prev = h29.get(sym, {}).get("box_oos", {})
        prev_sort = prev.get("sortino"); prev_n = prev.get("trades")
        prev_str = (f"H29 OOS={prev_sort:+.2f}/n={prev_n}" if isinstance(prev_sort, (int, float))
                    else "H29 n/a")
        print(f"\n  {sym} ({prev_str}):")
        for tag, r in (("A", ra), ("B", rb)):
            print(f"    var {tag} | full univ={r['universe_full']:>3} → aligned={r['aligned_full']:>3} → tr={r['trades_full']:>3} "
                  f"Sortino={r['sortino_full']:+.2f} | OOS tr={r['trades_oos']:>2} "
                  f"Sortino={r['sortino_oos']:+.2f} | {r['decision']:<5} | {r['reason']}")

    print("\nSUMMARY")
    for variant in ("A", "B"):
        n_go = sum(1 for r in results[variant].values() if r["decision"] == "GO")
        n_sweep = sum(1 for r in results[variant].values() if r["decision"] == "SWEEP")
        n_nogo = sum(1 for r in results[variant].values() if r["decision"] == "NO-GO")
        print(f"  Variant {variant}: GO={n_go}  SWEEP={n_sweep}  NO-GO={n_nogo}")
    n_total_go = sum(1 for v in ("A", "B")
                     for r in results[v].values() if r["decision"] == "GO")
    print(f"  Either variant GO somewhere: {n_total_go}")

    dump = {
        "seed": BOOT_SEED,
        "is_fraction": IS_FRACTION,
        "spec": {
            "t_endpoint": "p2", "max_length": bp.MAX_LENGTH_BARS,
            "variant_A_levels": list(bp.FIB_LEVELS_A),
            "variant_B_levels": list(bp.FIB_LEVELS_B),
            "variant_A_anchor": "P2_price",
            "variant_B_anchor": "P1_price",
        },
        "results_by_variant": results,
        "h29_compare": {sym: h29.get(sym, {}) for sym in ORDER},
    }
    (REPO / "results" / "_h30_run.json").write_text(json.dumps(dump, indent=2, default=str))
    print(f"\nWrote {REPO/'results'/'_h30_run.json'}")
    print("DONE.")


if __name__ == "__main__":
    main()
