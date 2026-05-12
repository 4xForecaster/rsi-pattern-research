#!/usr/bin/env python3
"""H13 — Controlled ablation over the three spec-discrepancy knobs.

Knobs (all else held at Scheme D):
  1. Detector: loose-M (current) vs strict-M
  2. Initial stop: structural-only (current) vs structural OR entry-1xATR(14)
     whichever is FURTHER from entry (lower price for a long)
  3. Range: pre-P1 (current, [P1-60, P1)) vs pre-entry (the M's inner trough,
     i.e. min(low) inside the M's span)

Cells:
  baseline : loose-M / structural / pre-P1
  v1_strict: strict-M / structural / pre-P1
  v2_atr   : loose-M / wider-stop / pre-P1
  v3_range : loose-M / structural / pre-entry
  v_all    : strict-M / wider-stop / pre-entry

For each cell: rebuild trade list, retag FLD bias, apply Scheme D multipliers
(0/1/3), build equity curve, summarize.
"""
from __future__ import annotations
import pathlib, sys
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rsi_pattern import data as data_mod
from rsi_pattern import indicators, fld
from rsi_pattern import position_sizing as ps
from rsi_pattern.position_sizing import (
    FibTrade, compute_fib_targets, simulate_fib_trade, TRAIL_ACTIVATION_FACTOR,
)
from rsi_pattern.patterns import detect_m, PatternConfig
from rsi_pattern.patterns_strict import detect_strict_m, StrictPatternConfig
from rsi_pattern import risk_metrics as rm

DEFAULT_DATA_ROOT = pathlib.Path.home() / "Documents" / "rsi-data"
if DEFAULT_DATA_ROOT.exists():
    data_mod.DATA_DIR = DEFAULT_DATA_ROOT

# Scheme D — locked from Step 1
MULTIPLIERS = {"bullish": 0.0, "neutral": 1.0, "bearish": 3.0, "unknown": 1.0}


# ---------- ATR(14) helper (Wilder smoothing) ----------

def atr14(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# ---------- M-pattern abstraction across loose/strict detectors ----------

def loose_patterns(df: pd.DataFrame, rsi_col: str = "rsi14"):
    """Yield (p1_idx, p2_idx, completed_bool) tuples."""
    rsi = df[rsi_col].dropna()
    for p in detect_m(rsi):
        if p.completed_idx is None:
            continue
        yield int(p.anchors[0]), int(p.anchors[1]), True


def strict_patterns(df: pd.DataFrame, rsi_col: str = "rsi14"):
    """Yield (p1_idx, last_major_idx, completed_bool) using strict-M."""
    rsi = df[rsi_col].dropna()
    for s in detect_strict_m(rsi):
        if s.completion_idx is None:
            continue
        yield int(s.first_major_peak_idx), int(s.last_major_peak_idx), True


# ---------- Range computations ----------

def range_pre_p1(df: pd.DataFrame, p1_idx: int) -> tuple[float, int]:
    """Current code's rule. Returns (range_size, anchor_low_idx)."""
    if p1_idx <= 0:
        return 0.0, p1_idx
    lookback = min(p1_idx, 60)
    seg = df.iloc[p1_idx - lookback:p1_idx]
    low_pos = int(seg["low"].values.argmin() + (p1_idx - lookback))
    price_low = float(df["low"].iloc[low_pos])
    price_high = float(df["high"].iloc[p1_idx])
    return price_high - price_low, low_pos


def range_pre_entry(df: pd.DataFrame, p1_idx: int, last_anchor_idx: int) -> tuple[float, int]:
    """The M's inner trough: min(low) over the M's span [P1, last_anchor].

    'last_anchor' = P2 for loose-M, last_major_peak for strict-M.
    Captures the price drop INSIDE the M pattern rather than the rise-origin
    floor that precedes it.
    """
    if last_anchor_idx <= p1_idx:
        # Degenerate: fall back to pre-P1 to avoid a 0-range trade
        return range_pre_p1(df, p1_idx)
    seg = df.iloc[p1_idx:last_anchor_idx + 1]
    low_pos = int(seg["low"].values.argmin() + p1_idx)
    price_low = float(df["low"].iloc[low_pos])
    price_high = float(df["high"].iloc[p1_idx])
    return price_high - price_low, low_pos


# ---------- Trade construction with knob switches ----------

def build_trades_one_cell(
    df: pd.DataFrame,
    pattern_iter,                # generator yielding (p1, last_anchor, completed)
    range_rule: str,             # "pre_p1" | "pre_entry"
    stop_rule: str,              # "structural" | "wider_atr"
    atr_series: pd.Series,
) -> list[FibTrade]:
    out = []
    n = len(df)
    for p1_idx, last_anchor_idx, _ in pattern_iter:
        entry_idx = p1_idx + 1
        if entry_idx >= n:
            continue
        entry_price = float(df["close"].iloc[entry_idx])

        if range_rule == "pre_p1":
            range_size, lo_idx = range_pre_p1(df, p1_idx)
        elif range_rule == "pre_entry":
            range_size, lo_idx = range_pre_entry(df, p1_idx, last_anchor_idx)
        else:
            raise ValueError(range_rule)
        if range_size <= 0:
            continue

        struct_stop = float(df["low"].iloc[lo_idx])
        if stop_rule == "structural":
            init_stop = struct_stop
        elif stop_rule == "wider_atr":
            atr_val = float(atr_series.iloc[entry_idx]) if not np.isnan(atr_series.iloc[entry_idx]) else 0.0
            atr_stop = entry_price - atr_val
            # For a long, wider/safer = lower stop
            init_stop = min(struct_stop, atr_stop) if atr_val > 0 else struct_stop
        else:
            raise ValueError(stop_rule)

        # Skip if stop is above or at entry (shouldn't happen but guard)
        if init_stop >= entry_price:
            continue

        targets = compute_fib_targets(entry_price, range_size, "long")
        t = FibTrade(
            direction="long",
            entry_idx=entry_idx,
            entry_price=entry_price,
            range_size=range_size,
            range_high_idx=p1_idx,
            range_low_idx=lo_idx,
            initial_stop=init_stop,
            targets=targets,
        )
        t = simulate_fib_trade(df, t, max_bars=200,
                               trail_activation_factor=TRAIL_ACTIVATION_FACTOR)
        out.append(t)
    return out


# ---------- Orchestration ----------

CELLS = [
    # (label, detector, range_rule, stop_rule)
    ("baseline (loose / struct / pre-P1)", "loose",  "pre_p1",   "structural"),
    ("v1 strict-M",                         "strict", "pre_p1",   "structural"),
    ("v2 wider stop (ATR)",                 "loose",  "pre_p1",   "wider_atr"),
    ("v3 pre-entry range",                  "loose",  "pre_entry","structural"),
    ("v_all (strict + wider + pre-entry)",  "strict", "pre_entry","wider_atr"),
]


def main():
    df = indicators.add_rsi(data_mod.load_dxy("daily"))
    df["atr14"] = atr14(df)
    bias = fld.fld_bias(df)

    print(f"Daily DXY: {len(df)} bars, {df.index[0].date()} → {df.index[-1].date()}")
    print()

    summaries = []
    for label, det, range_rule, stop_rule in CELLS:
        if det == "loose":
            it = list(loose_patterns(df))
        else:
            it = list(strict_patterns(df))
        trades = build_trades_one_cell(df, iter(it), range_rule, stop_rule, df["atr14"])

        # Tag FLD bias at entry and apply Scheme D multipliers
        records = []
        for t in trades:
            if t.exit_idx is None or t.r_multiple is None:
                continue
            entry_ts = df.index[t.entry_idx]
            lbl = bias.loc[entry_ts, "bias_label"] if entry_ts in bias.index else "unknown"
            mult = MULTIPLIERS.get(lbl, 1.0)
            if mult == 0:
                continue
            records.append(rm.TradeRecord(
                entry_date=pd.Timestamp(entry_ts),
                exit_date=pd.Timestamp(df.index[t.exit_idx]),
                r_multiple=float(t.r_multiple),
                multiplier=float(mult),
            ))

        equity = rm.build_equity_curve(records, initial_capital=1.0, risk_per_trade=0.01)
        s = rm.summarize(label, records, equity)
        # Also stash trade count BEFORE FLD skip for diagnostics
        s["trades_pre_fld_skip"] = sum(1 for t in trades if t.r_multiple is not None)
        summaries.append(s)

    # Print table
    headers = ["Cell", "Trades", "Mean R", "Total R/yr",
               "Sharpe", "Sortino", "Calmar", "MAR", "Max DD"]
    rows = []
    for s in summaries:
        rows.append([
            s["scheme"],
            f"{s['trades']:d}",
            f"{s['mean_R']:+.2f}",
            f"{s['total_R_per_year']:+.2f}",
            f"{s['sharpe']:+.2f}",
            f"{s['sortino']:+.2f}",
            f"{s['calmar']:+.2f}",
            f"{s['mar']:+.2f}",
            f"{s['max_dd'] * 100:+.2f}%",
        ])
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    fmt = " | ".join(f"{{:<{w}}}" for w in widths)
    sep = "-+-".join("-" * w for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for r in rows:
        print(fmt.format(*r))
    print()

    # Apply selection rule
    valid = [s for s in summaries if s["trades"] >= 20]
    insufficient = [s for s in summaries if s["trades"] < 20]
    if insufficient:
        print("Cells with <20 trades (excluded from selection):")
        for s in insufficient:
            print(f"  - {s['scheme']}: {s['trades']} trades")
        print()

    if not valid:
        print("ERROR: no cell has ≥20 trades — selection cannot proceed.")
        return summaries

    # 1) Highest Sortino
    valid.sort(key=lambda s: -s["sortino"])
    best = valid[0]
    top_sortino = best["sortino"]
    # 2) Within 5%, break on Mean R
    near = [s for s in valid if abs(s["sortino"] - top_sortino) / abs(top_sortino) <= 0.05]
    if len(near) > 1:
        near.sort(key=lambda s: (-s["mean_R"], -s["trades"]))
        best = near[0]

    print(f"WINNER: {best['scheme']}")
    print(f"  Sortino={best['sortino']:+.2f}  MeanR={best['mean_R']:+.2f}  "
          f"Trades={best['trades']}  MaxDD={best['max_dd']*100:+.2f}%")

    return summaries


if __name__ == "__main__":
    main()
