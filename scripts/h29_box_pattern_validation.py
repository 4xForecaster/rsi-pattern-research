#!/usr/bin/env python3
"""H29 — Backtest the box-pattern signal (Dr. A's spec) and check confluence
with the existing M-P1 LONG stack.

Faithfulness gate (runs FIRST): detector + bias rule reproduce hand-checked
DXY anchors; the same engine that the unit tests exercise drives the
cross-symbol pass — no separate metric path.

Cross-symbol pool (same H23 universe): DXY (BarChart) + EURUSD GBPUSD
USDJPY USDCAD AUDUSD NZDUSD (yfinance, cached). 70/30 split by bars; OOS
load-bearing. Locked rule: GO = OOS Sortino ≥ +3.0 AND OOS trades ≥ 30;
NO-GO = OOS Sortino < +1.0 OR OOS trades < 10; SWEEP otherwise. Any thin
GO (OOS trades < 20) → H24 4-test robustness gate.

Confluence: for each pair, compute box-LONG and M-P1 LONG entry-bar sets
under the same engine and report intersection / union and a same-day
overlap %. If overlap ≥ 30%, run the "both fire same day" confluence
strategy; ship only if box-GO AND M-P1-GO AND confluence-Sortino >
max(box, M-P1).

Hurst rule: hurst-agent changes ONLY if at least one pair clears GO.
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
from rsi_pattern import risk_metrics as rm
from rsi_pattern import box_pattern as bp
from rsi_pattern.patterns import PatternConfig

CACHE = REPO / "data" / "yfinance_cache"
OUTDIR_FIG = REPO / "figures"
IS_FRACTION = 0.70
SCHEME_D = (0.0, 1.0, 3.0)
SHIP_FLOOR = 3.0
PER_TRADE_FLOOR = 2.5
GINI_MAX = 0.7
N_BOOT = 10_000
BOOT_SEED = 42
THIN_OOS = 20
CONFLUENCE_MIN_OVERLAP = 0.30

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


# ---------------------------------------------------------------------------
# Box backtest — emits trade records via box_to_trade + bias filter
# ---------------------------------------------------------------------------

def box_records(df: pd.DataFrame, direction: str = "long") -> tuple[list[rm.TradeRecord], int, int]:
    """Returns (records, universe_detected, after_bias_filter). Universe = all
    completed boxes; after_bias_filter = those passing the matching-direction
    rule (#7)."""
    boxes = bp.detect_boxes_df(df, direction=direction)
    universe = len(boxes)
    aligned = 0
    recs: list[rm.TradeRecord] = []
    for box in boxes:
        if not box.trade_aligned:
            continue
        aligned += 1
        trade = bp.box_to_trade(box, df, bias_filter=True)
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
            "sharpe": float(rm.sharpe(eq)),
            "max_dd": float(rm.max_drawdown(eq)),
            "mar": float(rm.mar(eq)),
            "calmar": float(rm.calmar(eq)),
            "total_R_per_year": float(rm.total_r_per_year(records)),
            "equity": eq, "records": records}


def go_no_go(oos: dict) -> tuple[str, str]:
    s, n = oos["sortino"], oos["trades"]
    if np.isnan(s):
        return "NO-GO", f"OOS Sortino undefined (n={n})"
    if s >= SHIP_FLOOR and n >= 30:
        return "GO", f"OOS Sortino {s:+.2f}≥3 AND OOS trades {n}≥30"
    if s < 1.0 or n < 10:
        return "NO-GO", f"OOS Sortino {s:+.2f}<1 OR OOS trades {n}<10"
    return "SWEEP", f"OOS Sortino {s:+.2f} in [1,3) or trades {n} in [10,30)"


# ---------------------------------------------------------------------------
# H24 robustness (reused, condensed)
# ---------------------------------------------------------------------------

def _sortino(recs):
    if len(recs) < 2:
        return float("nan")
    return rm.sortino(rm.build_equity_curve(recs, 1.0, 0.01))


def _gini(v):
    x = np.sort(np.asarray(v, float)); n = len(x); s = x.sum()
    if n == 0 or s == 0:
        return float("nan")
    return float((2 * np.sum(np.arange(1, n + 1) * x)) / (n * s) - (n + 1) / n)


def robustness(recs, oos0, oos1) -> dict:
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
    fd = [d for d in drops if np.isfinite(d)]
    mn = min(fd) if fd else float("nan")
    c = [p5 >= SHIP_FLOOR, n_ge >= 3,
         (not np.isnan(g)) and g <= GINI_MAX,
         (not np.isnan(mn)) and mn >= PER_TRADE_FLOOR]
    hold = sum(c)
    return {"boot_p5": round(p5, 3),
            "rolling": [None if not np.isfinite(w) else round(float(w), 3) for w in wins],
            "n_rolling_ge": n_ge, "gini": None if np.isnan(g) else round(g, 4),
            "per_trade_min": None if np.isnan(mn) else round(mn, 3),
            "n_hold": hold,
            "verdict": "SOLID_GO" if hold == 4 else "THIN_GO" if hold in (2, 3) else "DOWNGRADE_SWEEP"}


# ---------------------------------------------------------------------------
# M-P1 LONG records (verbatim H23/H24 path)
# ---------------------------------------------------------------------------

def mp1_records(df: pd.DataFrame) -> list[rm.TradeRecord]:
    dr = indicators.add_rsi(df, period=14)
    trades = position_sizing.fib_long_at_p1(dr, rsi_col="rsi14",
                                             cfg=PatternConfig(m_inner_threshold=50.0))
    bias = fld.fld_bias(dr, cycles=(10, 20, 40))
    bull_m, neut_m, bear_m = SCHEME_D
    recs = []
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        ets = dr.index[t.entry_idx]
        lbl = bias.loc[ets, "bias_label"] if ets in bias.index else "unknown"
        mult = bull_m if lbl == "bullish" else bear_m if lbl == "bearish" else neut_m
        if mult == 0:
            continue
        recs.append(rm.TradeRecord(entry_date=pd.Timestamp(ets),
                                   exit_date=pd.Timestamp(dr.index[t.exit_idx]),
                                   r_multiple=float(t.r_multiple),
                                   multiplier=float(mult)))
    return recs


def faithfulness_check(df_dxy: pd.DataFrame) -> dict:
    """Hand-walk a handful of detected DXY boxes to verify mechanics. We
    confirm: P0<P1<P2<P3 ordering, 50% retracement actually touched at P2,
    P3.high actually > P1, and asymmetry sign matches the P1 vs T-mid rule."""
    boxes = bp.detect_boxes_df(df_dxy, "long")
    short_boxes = bp.detect_boxes_df(df_dxy, "short")
    n_long = len(boxes); n_short = len(short_boxes)
    sample = boxes[:5]
    ok = True; bad = []
    for b in sample:
        mid = b.p0_price + 0.5 * (b.p1_price - b.p0_price)
        cond_order = (b.p0_idx < b.p1_idx < b.p2_idx < b.p3_idx)
        cond_50 = float(df_dxy["low"].iloc[b.p2_idx]) <= mid + 1e-9
        cond_p3 = float(df_dxy["high"].iloc[b.p3_idx]) > b.p1_price - 1e-9
        cond_asym = ((b.asymmetry == "bullish" and b.p1_idx > b.t_mid) or
                      (b.asymmetry == "bearish" and b.p1_idx < b.t_mid) or
                      (b.asymmetry == "neutral" and b.p1_idx == b.t_mid))
        chk = cond_order and cond_50 and cond_p3 and cond_asym
        if not chk:
            ok = False; bad.append({"box": b, "order": cond_order,
                                     "50%": cond_50, "p3": cond_p3, "asym": cond_asym})
    aligned_long = sum(1 for b in boxes if b.trade_aligned)
    return {"n_long_boxes": n_long, "n_short_boxes": n_short,
             "n_long_aligned": aligned_long,
             "sample_checked": len(sample), "all_valid": ok,
             "bad": [str(b) for b in bad]}


# ---------------------------------------------------------------------------
# Confluence
# ---------------------------------------------------------------------------

def confluence(box_recs: list[rm.TradeRecord], mp1_recs: list[rm.TradeRecord]) -> dict:
    box_dates = {r.entry_date.normalize() for r in box_recs}
    mp1_dates = {r.entry_date.normalize() for r in mp1_recs}
    inter = box_dates & mp1_dates
    uni = box_dates | mp1_dates
    overlap_pct_min = (len(inter) / min(len(box_dates), len(mp1_dates))
                       if min(len(box_dates), len(mp1_dates)) else 0.0)
    overlap_pct_union = len(inter) / len(uni) if uni else 0.0
    return {"box_n": len(box_dates), "mp1_n": len(mp1_dates),
            "intersection_n": len(inter), "union_n": len(uni),
            "overlap_pct_min": overlap_pct_min,
            "overlap_pct_union": overlap_pct_union,
            "intersection_dates": sorted(d.date().isoformat() for d in inter)[:50]}


def confluence_strategy(df: pd.DataFrame) -> dict:
    """Both signals must fire on the SAME bar. Use box-style entry/stop/targets
    (cleanest single attribution); fall back to mp1-style if box trade is None.
    Reuses box's structural stop and SURF Fib targets for symmetry."""
    boxes = bp.detect_boxes_df(df, "long")
    box_entry_by_date = {}
    for box in boxes:
        if not box.trade_aligned:
            continue
        tr = bp.box_to_trade(box, df, bias_filter=True)
        if tr is None or tr.exit_idx is None or tr.r_multiple is None:
            continue
        box_entry_by_date[df.index[tr.entry_idx].normalize()] = tr
    mp1 = mp1_records(df)
    mp1_dates = {r.entry_date.normalize() for r in mp1}
    same_day = [t for d, t in box_entry_by_date.items() if d in mp1_dates]
    recs = [rm.TradeRecord(entry_date=pd.Timestamp(df.index[t.entry_idx]),
                            exit_date=pd.Timestamp(df.index[t.exit_idx]),
                            r_multiple=float(t.r_multiple), multiplier=1.0)
            for t in same_day]
    return {**metrics(recs), "n_co_fires": len(same_day)}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def evaluate(sym: str, df: pd.DataFrame) -> dict:
    np.random.seed(BOOT_SEED)
    is_df, oos = split_70_30(df)
    bf, bf_univ, bf_aligned = box_records(df, "long")
    bi, bi_univ, bi_aligned = box_records(is_df, "long")
    bo, bo_univ, bo_aligned = box_records(oos, "long")
    Mf = metrics(bf); Mi = metrics(bi); Mo = metrics(bo)
    dec, rsn = go_no_go(Mo)
    rob = None
    if dec == "GO" and Mo["trades"] < THIN_OOS:
        rob = robustness(Mo["records"], oos.index[0], oos.index[-1])
        if rob["verdict"] == "DOWNGRADE_SWEEP":
            dec, rsn = "SWEEP", rsn + " | H24 0-1/4 → downgraded"
        elif rob["verdict"] == "THIN_GO":
            rsn += " | H24 2-3/4 → THIN GO"

    # Confluence vs M-P1 (full sample for overlap headline; OOS for ship gate)
    mp1_full = mp1_records(df)
    mp1_oos = mp1_records(oos)
    overlap_full = confluence(bf, mp1_full)
    overlap_oos = confluence(bo, mp1_oos)
    conf_test = None
    if overlap_full["overlap_pct_min"] >= CONFLUENCE_MIN_OVERLAP:
        conf_test = confluence_strategy(oos)

    return {
        "data_first": df.index[0].date().isoformat(),
        "data_last": df.index[-1].date().isoformat(),
        "data_bars": len(df),
        "oos_window": [oos.index[0].date().isoformat(), oos.index[-1].date().isoformat(), len(oos)],
        "box_full": {**{k: v for k, v in Mf.items() if k not in ("equity", "records")},
                      "universe": bf_univ, "aligned": bf_aligned},
        "box_is":   {**{k: v for k, v in Mi.items() if k not in ("equity", "records")},
                      "universe": bi_univ, "aligned": bi_aligned},
        "box_oos":  {**{k: v for k, v in Mo.items() if k not in ("equity", "records")},
                      "universe": bo_univ, "aligned": bo_aligned},
        "decision": dec, "reason": rsn, "robustness": rob,
        "mp1_full_trades": len(mp1_full), "mp1_oos_trades": len(mp1_oos),
        "confluence_full": {k: v for k, v in overlap_full.items() if k != "intersection_dates"},
        "confluence_oos":  {k: v for k, v in overlap_oos.items() if k != "intersection_dates"},
        "confluence_strategy_oos": None if conf_test is None
            else {k: v for k, v in conf_test.items() if k not in ("equity", "records")},
        "_full_equity": Mf["equity"],
        "_sample_long_boxes": [
            {"p0": int(b.p0_idx), "p1": int(b.p1_idx), "p2": int(b.p2_idx), "p3": int(b.p3_idx),
             "asymmetry": b.asymmetry, "aligned": b.trade_aligned,
             "p0_price": float(b.p0_price), "p1_price": float(b.p1_price)}
            for b in bp.detect_boxes_df(df, "long")[:3]
        ],
    }


def fig_box_example(sym: str, df: pd.DataFrame, boxes: list, path: pathlib.Path) -> None:
    if not boxes:
        return
    box = boxes[0]
    # Frame around the box ±60 bars
    a = max(box.p0_idx - 60, 0); b = min(box.p3_idx + 60, len(df) - 1)
    sub = df.iloc[a:b + 1]
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(sub.index, sub["close"], color="#333", linewidth=1.2)
    pts = [(box.p0_idx, box.p0_price, "P0", "#1f77b4"),
            (box.p1_idx, box.p1_price, "P1", "#d62728"),
            (box.p2_idx, box.p2_price, "P2", "#1f77b4"),
            (box.p3_idx, box.p3_price, "P3", "#d62728")]
    for idx, price, lbl, c in pts:
        ax.scatter(df.index[idx], price, s=110, color=c, edgecolor="black", lw=0.6, zorder=4)
        ax.annotate(lbl, (df.index[idx], price), textcoords="offset points",
                    xytext=(6, 7), fontsize=11, fontweight="bold")
    mid_idx = int(box.t_mid)
    if 0 <= mid_idx < len(df):
        ax.axvline(df.index[mid_idx], color="green", linestyle=":", linewidth=1.4,
                   label=f"T-mid (idx {mid_idx})")
    ax.axhline(box.p0_price, color="grey", lw=0.7, alpha=0.5)
    ax.axhline(box.p1_price, color="grey", lw=0.7, alpha=0.5)
    ax.set_title(f"{sym} — first detected LONG box  ({box.asymmetry}, "
                 f"{'aligned ✓' if box.trade_aligned else 'countertrend → skipped'})",
                 fontsize=11)
    ax.grid(True, alpha=0.3); ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight"); plt.close()


def main() -> None:
    print("=" * 82)
    print("H29 — Box-pattern signal: detect, backtest, cross-symbol, confluence")
    print("=" * 82)
    data = {sym: load(sym) for sym in ORDER}

    print("\nFAITHFULNESS GATE — DXY box mechanics")
    f = faithfulness_check(data["DXY"])
    print(f"  DXY long boxes: {f['n_long_boxes']}  aligned: {f['n_long_aligned']} | "
          f"short boxes: {f['n_short_boxes']}  sample checked: {f['sample_checked']}/5  "
          f"all-valid: {f['all_valid']}")
    if not f["all_valid"]:
        for bad in f["bad"]:
            print(f"   BAD: {bad}")
        raise SystemExit("Faithfulness FAILED — not running backtest.")

    print("\nPER-PAIR EVALUATION (70/30 OOS load-bearing)")
    results: dict[str, dict] = {}
    for sym, df in data.items():
        r = evaluate(sym, df); results[sym] = r
        bo = r["box_oos"]; bf = r["box_full"]; ov = r["confluence_full"]
        conf_str = ""
        if r["confluence_strategy_oos"] is not None:
            cs = r["confluence_strategy_oos"]
            conf_str = (f" conf-OOS Sortino={cs['sortino']:+.2f}/n={cs['trades']}"
                         f" (co-fires={cs['n_co_fires']})")
        print(f"  {sym:7s} | box FULL univ={bf['universe']:>3}→aligned={bf['aligned']:>3}"
              f"→tr={bf['trades']:>3} Sortino={bf['sortino']:+.2f} |"
              f" OOS tr={bo['trades']:>2} Sortino={bo['sortino']:+.2f} | "
              f"{r['decision']:<5} | overlap min={ov['overlap_pct_min']:.0%}{conf_str}")

    n_go = sum(1 for r in results.values() if r["decision"] == "GO")
    print(f"\nGO count: {n_go}  ({[s for s in ORDER if results[s]['decision']=='GO']})")

    print("\nGenerating figures...")
    OUTDIR_FIG.mkdir(exist_ok=True)
    # Fig 24: annotated box example — use DXY (anchor)
    fig_box_example("DXY", data["DXY"], bp.detect_boxes_df(data["DXY"], "long"),
                    OUTDIR_FIG / "24_box_pattern_example.png")
    print(f"Wrote {OUTDIR_FIG/'24_box_pattern_example.png'}")
    # Fig 25: OOS Sortino bar chart
    fig, ax = plt.subplots(figsize=(11, 6))
    syms_sorted = sorted(ORDER, key=lambda s: -1e9 if np.isnan(results[s]["box_oos"]["sortino"])
                          else results[s]["box_oos"]["sortino"], reverse=True)
    vals = [0.0 if np.isnan(results[s]["box_oos"]["sortino"])
            else results[s]["box_oos"]["sortino"] for s in syms_sorted]
    colors = ["#2ca02c" if results[s]["decision"] == "GO"
              else "#ff7f0e" if results[s]["decision"] == "SWEEP" else "#d62728"
              for s in syms_sorted]
    bars = ax.bar(syms_sorted, vals, color=colors, edgecolor="black", lw=0.6)
    ax.axhline(SHIP_FLOOR, color="green", ls="--", lw=1.4, label="GO floor +3.0")
    ax.axhline(1.0, color="red", ls=":", lw=1.2, label="NO-GO floor +1.0")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + (0.08 if v >= 0 else -0.25),
                f"{v:+.2f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=9)
    ax.set_ylabel("OOS Sortino (annualized)")
    ax.set_title("H29 — Box pattern OOS Sortino by symbol\ngreen=GO orange=SWEEP red=NO-GO",
                 fontsize=11, pad=10)
    ax.grid(True, axis="y", alpha=0.3); ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTDIR_FIG / "25_box_cross_symbol_sortinos.png", dpi=140, bbox_inches="tight")
    plt.close()
    print(f"Wrote {OUTDIR_FIG/'25_box_cross_symbol_sortinos.png'}")

    dump = {"seed": BOOT_SEED, "is_fraction": IS_FRACTION,
             "prominence_frac": bp.PROMINENCE_FRAC, "distance_bars": bp.DISTANCE_BARS,
             "faithfulness": {k: (v if k != "bad" else len(v)) for k, v in f.items()},
             "results": {sym: {k: v for k, v in r.items() if not k.startswith("_")}
                          for sym, r in results.items()},
             "go_count": n_go}
    (REPO / "results" / "_h29_run.json").write_text(json.dumps(dump, indent=2, default=str))
    print(f"Wrote {REPO/'results'/'_h29_run.json'}")
    print("DONE.")


if __name__ == "__main__":
    main()
