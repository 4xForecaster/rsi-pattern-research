"""Intraday execution engine — strict-M / FLD / SURF-Fib pipeline.

Bundles pattern detection (strict or loose), range definition, stop logic,
trade simulation, and overlap-aware MTM trade-record construction so
H14 phase-1/2/3 sweeps can share one source of truth.

Calibrated for 5m and 15m DXY per H14 Phase 1.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence
import numpy as np
import pandas as pd

from .patterns import detect_m, PatternConfig
from .patterns_strict import detect_strict_m, StrictPatternConfig
from .position_sizing import (
    FibTrade, compute_fib_targets, simulate_fib_trade, TRAIL_ACTIVATION_FACTOR,
)
from .risk_metrics import MTMTrade


# --- Hurst FLD cycles per intraday timeframe (canonical 2× harmonic ladder) ---
INTRADAY_FLD_CYCLES = {
    "5m":  (40, 80, 160),
    "15m": (32, 64, 128),
}

# --- Time-stop in bars per timeframe (≈ 1× longest FLD cycle) ---
INTRADAY_TIME_STOP_BARS = {
    "5m":  160,
    "15m": 128,
}

# --- Spread (fractional) per timeframe — H14 conservative defaults ---
INTRADAY_SPREAD = {
    "5m":  0.0003,   # 3 bps
    "15m": 0.00025,  # 2.5 bps
}

# --- Calibrated strict-M thresholds from H14 Phase 1.2 grid sweep ---
INTRADAY_STRICT_CFG = StrictPatternConfig(
    rise_origin_below=30.0,
    major_peak_min=72.0,
    wiggle_trough_floor=72.0,
    completion_threshold=50.0,
    max_rise_bars=60,
    max_top_zone_bars=60,
    max_completion_bars=60,
)


# --- ATR(14) Wilder smoothing ---
def atr14(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# --- Pattern iteration (unified loose / strict interface) ---
def iter_patterns(rsi: pd.Series, detector: str, strict_cfg: Optional[StrictPatternConfig] = None):
    """Yield (p1_idx, last_anchor_idx) for every completed M pattern."""
    if detector == "strict":
        for s in detect_strict_m(rsi, strict_cfg or INTRADAY_STRICT_CFG):
            if s.completion_idx is None:
                continue
            yield int(s.first_major_peak_idx), int(s.last_major_peak_idx)
    elif detector == "loose":
        for p in detect_m(rsi):
            if p.completed_idx is None:
                continue
            yield int(p.anchors[0]), int(p.anchors[1])
    else:
        raise ValueError(f"unknown detector {detector!r}")


# --- Range computations ---
def range_pre_p1(df: pd.DataFrame, p1_idx: int, lookback: int) -> tuple[float, int]:
    if p1_idx <= 0:
        return 0.0, p1_idx
    lb = min(p1_idx, lookback)
    seg = df.iloc[p1_idx - lb:p1_idx]
    low_pos = int(seg["low"].values.argmin() + (p1_idx - lb))
    price_low = float(df["low"].iloc[low_pos])
    price_high = float(df["high"].iloc[p1_idx])
    return price_high - price_low, low_pos


def range_pre_entry(df: pd.DataFrame, p1_idx: int, last_anchor_idx: int) -> tuple[float, int]:
    if last_anchor_idx <= p1_idx:
        return range_pre_p1(df, p1_idx, lookback=60)
    seg = df.iloc[p1_idx:last_anchor_idx + 1]
    low_pos = int(seg["low"].values.argmin() + p1_idx)
    price_low = float(df["low"].iloc[low_pos])
    price_high = float(df["high"].iloc[p1_idx])
    return price_high - price_low, low_pos


# --- Build a list of FibTrade objects for one config ---
def build_fib_trades(
    df: pd.DataFrame,
    detector: str = "strict",
    range_rule: str = "pre_p1",
    lookback_bars: int = 160,
    stop_rule: str = "structural",
    time_stop_bars: int = 160,
    strict_cfg: Optional[StrictPatternConfig] = None,
    rsi_col: str = "rsi14",
    atr_series: Optional[pd.Series] = None,
) -> list[FibTrade]:
    rsi = df[rsi_col].dropna()
    n = len(df)
    trades: list[FibTrade] = []
    for p1_idx, last_anchor_idx in iter_patterns(rsi, detector, strict_cfg):
        entry_idx = p1_idx + 1
        if entry_idx >= n:
            continue
        entry_price = float(df["close"].iloc[entry_idx])

        if range_rule == "pre_p1":
            range_size, lo_idx = range_pre_p1(df, p1_idx, lookback_bars)
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
            atr_val = 0.0
            if atr_series is not None and entry_idx < len(atr_series):
                v = atr_series.iloc[entry_idx]
                atr_val = 0.0 if pd.isna(v) else float(v)
            atr_stop = entry_price - atr_val
            init_stop = min(struct_stop, atr_stop) if atr_val > 0 else struct_stop
        else:
            raise ValueError(stop_rule)

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
        t = simulate_fib_trade(df, t, max_bars=time_stop_bars,
                               trail_activation_factor=TRAIL_ACTIVATION_FACTOR)
        trades.append(t)
    return trades


# --- Convert FibTrade to MTMTrade for overlap-aware equity ---
def fib_to_mtm(
    trades: Sequence[FibTrade],
    df: pd.DataFrame,
    multipliers: Sequence[float],
    spread: float,
) -> list[MTMTrade]:
    out: list[MTMTrade] = []
    for t, mult in zip(trades, multipliers):
        if t.exit_idx is None or t.exit_price is None or mult == 0:
            continue
        # closes during life: from entry through exit bar (close at each bar)
        life_closes = df["close"].iloc[t.entry_idx:t.exit_idx + 1].copy()
        out.append(MTMTrade(
            entry_idx=t.entry_idx,
            exit_idx=t.exit_idx,
            entry_date=pd.Timestamp(df.index[t.entry_idx]),
            exit_date=pd.Timestamp(df.index[t.exit_idx]),
            entry_price=float(t.entry_price),
            initial_stop=float(t.initial_stop),
            exit_price=float(t.exit_price),
            direction=t.direction,
            multiplier=float(mult),
            spread=float(spread),
            closes=life_closes,
        ))
    return out
