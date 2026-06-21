#!/usr/bin/env python3
"""H30c — Chain-conditional box-pattern backtest.

Adds the chain context lens to the H30b backtest: only take a trade when
the box is at chain_index ≥ K (i.e. inside an active chain of length ≥
K+1). Tests Dr. A's intuition that chain context matters by comparing:
  (a) standalone H30b baseline (chain_mode=False, single-direction)
  (b) chain-mode N≥1 (all chained boxes, both directions; the chain
      detector's natural output)
  (c) chain-mode N≥2 (continuation boxes only — skip the first box of
      every chain because at box-1 we don't yet know whether a chain
      will form)
  (d) chain-mode N≥3 (extra-strict continuation; chain of length ≥3)

Same engine path as H30b (Variant A targets, P2-anchored trail, locked
GO/SWEEP/NO-GO rule). H24 robustness gate on anything that flips GO.

H30b is preserved (separate `_h30_run.json` exists). This script writes
`_h30c_run.json`. H30 results doc gets a new "Box chaining and reversal"
section pointing here.
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
TARGET_VARIANT = "A"

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


def chained_records(df: pd.DataFrame, *, min_chain_index: int
                    ) -> tuple[list[rm.TradeRecord], int, int]:
    """Run the chained detector; filter to aligned boxes with chain_index ≥
    ``min_chain_index``; produce TradeRecords via Variant A. Returns
    (records, universe_after_chain_filter, aligned_count)."""
    boxes = bp.detect_boxes_df(df, chain_mode=True)
    filtered = [b for b in boxes if b.chain_index is not None
                                  and b.chain_index >= min_chain_index]
    universe = len(filtered)
    aligned = 0
    recs: list[rm.TradeRecord] = []
    for box in filtered:
        if not box.trade_aligned:
            continue
        aligned += 1
        trade = bp.box_to_trade(box, df, bias_filter=True,
                                 target_variant=TARGET_VARIANT)
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
    return {"trades": len(records),
            "sortino": float(rm.sortino(eq)),
            "max_dd": float(rm.max_drawdown(eq)),
            "_records": records}


def go_no_go(oos: dict) -> tuple[str, str]:
    s, n = oos["sortino"], oos["trades"]
    if np.isnan(s):
        return "NO-GO", f"OOS Sortino undefined (n={n})"
    if s >= SHIP_FLOOR and n >= 30:
        return "GO", f"OOS Sortino {s:+.2f}≥3 AND OOS trades {n}≥30"
    if s < 1.0 or n < 10:
        return "NO-GO", f"OOS Sortino {s:+.2f}<1 OR OOS trades {n}<10"
    return "SWEEP", f"OOS Sortino {s:+.2f} in [1,3) or trades {n} in [10,30)"


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


def evaluate_pair_chain(sym: str, df: pd.DataFrame, min_chain_index: int) -> dict:
    np.random.seed(BOOT_SEED)
    is_df, oos = split_70_30(df)
    fr, fu, fa = chained_records(df, min_chain_index=min_chain_index)
    or_, ou, oa = chained_records(oos, min_chain_index=min_chain_index)
    Mf = metrics(fr); Mo = metrics(or_)
    dec, rsn = go_no_go(Mo)
    rob = None
    if dec == "GO" and Mo["trades"] < THIN_OOS:
        rob = robustness(Mo["_records"], oos.index[0], oos.index[-1])
        if rob["verdict"] == "DOWNGRADE_SWEEP":
            dec, rsn = "SWEEP", rsn + " | H24 0-1/4 → downgraded"
        elif rob["verdict"] == "THIN_GO":
            rsn += " | H24 2-3/4 → THIN GO"
    return {
        "universe_full": fu, "aligned_full": fa,
        "trades_full": Mf["trades"], "sortino_full": round(Mf["sortino"], 3),
        "max_dd_full": round(Mf["max_dd"], 4),
        "universe_oos": ou, "aligned_oos": oa,
        "trades_oos": Mo["trades"], "sortino_oos": round(Mo["sortino"], 3),
        "max_dd_oos": round(Mo["max_dd"], 4),
        "decision": dec, "reason": rsn, "robustness": rob,
    }


def load_h30b_oos() -> dict:
    """Read the H30b OOS numbers from the existing _h30_run.json (Variant A)."""
    try:
        h30 = json.loads((REPO / "results" / "_h30_run.json").read_text())
        return {sym: h30["results_by_variant"]["A"][sym]
                for sym in ORDER if sym in h30["results_by_variant"]["A"]}
    except Exception:  # noqa: BLE001
        return {}


def main() -> None:
    print("=" * 84)
    print("H30c — Chain-conditional box-pattern (Variant A; chain_mode=True; H30b baseline cited)")
    print("=" * 84)
    data = {sym: load(sym) for sym in ORDER}
    h30b = load_h30b_oos()
    LENSES = (("N>=1", 0), ("N>=2", 1), ("N>=3", 2))

    print("\nDETECTOR SANITY — chain shape on full DXY history")
    boxes_dxy = bp.detect_boxes_df(data["DXY"], chain_mode=True)
    chains: dict[int, list] = {}
    for b in boxes_dxy:
        chains.setdefault(b.chain_id, []).append(b)
    lens_count = {k: 0 for k in (1, 2, 3, 4, 5)}
    rev_count = 0
    for cid, bs in chains.items():
        n = len(bs)
        lens_count.setdefault(n, 0)
        lens_count[n] = lens_count.get(n, 0) + 1
        if bs[0].reverses_chain_id is not None:
            rev_count += 1
    print(f"  DXY total chained boxes: {len(boxes_dxy)} in {len(chains)} chains")
    print(f"  Chain-length distribution: {dict(sorted(lens_count.items()))}")
    print(f"  Reversal-started chains: {rev_count}")
    longest_chain = max(chains.values(), key=len)
    print(f"  Longest chain: id={longest_chain[0].chain_id} dir={longest_chain[0].direction} "
          f"len={len(longest_chain)} bars={longest_chain[0].p0_idx}→{longest_chain[-1].p3_idx}")

    print("\nPER-PAIR (H30b baseline / chain N>=1 / N>=2 / N>=3) — Variant A OOS")
    results: dict[str, dict] = {sym: {} for sym in ORDER}
    for sym in ORDER:
        df = data[sym]
        print(f"\n  {sym}:")
        base = h30b.get(sym, {})
        s_base = base.get("sortino_oos"); n_base = base.get("trades_oos")
        dec_base = base.get("decision", "?")
        print(f"    H30b baseline (standalone) OOS Sortino={s_base} n={n_base} → {dec_base}")
        for label, mci in LENSES:
            r = evaluate_pair_chain(sym, df, min_chain_index=mci)
            results[sym][label] = r
            print(f"    chain {label:5s} full univ={r['universe_full']:>3} → aligned={r['aligned_full']:>3} "
                  f"→ tr={r['trades_full']:>3} S={r['sortino_full']:+.2f} | "
                  f"OOS univ={r['universe_oos']:>3} aligned={r['aligned_oos']:>3} tr={r['trades_oos']:>2} "
                  f"S={r['sortino_oos']:+.2f} MDD={r['max_dd_oos']*100:+.1f}% | {r['decision']}")

    print("\nSUMMARY (Variant A, OOS)")
    print(f"  {'Sym':6s} {'H30b':>10s} | {'N>=1 OOS':>10s} {'dec':<6s} | {'N>=2 OOS':>10s} {'dec':<6s} | {'N>=3 OOS':>10s} {'dec':<6s}")
    for sym in ORDER:
        b = h30b.get(sym, {})
        b_s = b.get("sortino_oos"); b_n = b.get("trades_oos"); b_d = b.get("decision", "?")
        cells = []
        for label, _ in LENSES:
            r = results[sym][label]
            cells.append((r['sortino_oos'], r['trades_oos'], r['decision']))
        bstr = f"{b_s:+.2f}/{b_n}" if isinstance(b_s, (int, float)) else "n/a"
        cstr = lambda c: f"{c[0]:+.2f}/{c[1]}"
        print(f"  {sym:6s} {bstr:>10s} | {cstr(cells[0]):>10s} {cells[0][2]:<6s} | "
              f"{cstr(cells[1]):>10s} {cells[1][2]:<6s} | {cstr(cells[2]):>10s} {cells[2][2]:<6s}")

    n_go = sum(1 for sym in ORDER for label, _ in LENSES
               if results[sym][label]["decision"] == "GO")
    print(f"\nGO count across all (pair × lens) cells: {n_go}")

    dump = {
        "seed": BOOT_SEED, "is_fraction": IS_FRACTION,
        "target_variant": TARGET_VARIANT,
        "lenses": [{"label": l, "min_chain_index": m} for l, m in LENSES],
        "h30b_baseline_oos": h30b,
        "results": results,
        "chain_sanity_dxy": {
            "total_boxes": len(boxes_dxy),
            "n_chains": len(chains),
            "length_distribution": dict(sorted(lens_count.items())),
            "reversal_started_chains": rev_count,
        },
    }
    (REPO / "results" / "_h30c_run.json").write_text(json.dumps(dump, indent=2, default=str))
    print(f"\nWrote {REPO/'results'/'_h30c_run.json'}")


if __name__ == "__main__":
    main()
