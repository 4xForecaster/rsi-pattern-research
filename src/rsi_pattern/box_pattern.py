"""Box-pattern signal — Dr. A's 4-point swing structure + Hurst time-asymmetry bias.

Spec (verbatim from H29 brief, LONG box; SHORT box mirrors):
  P0  swing LOW
  P1  subsequent swing HIGH (after P0)
  P2  first bar whose LOW ≤ midpoint(P0,P1) = P0 + 0.5·(P1 − P0)
      → "box pre-condition" established (need NOT break below P0)
  P3  first bar AFTER P2 whose HIGH > P1.high → "box confirmed"
  Height  = P1.price − P0.price
  Length  = P3.idx − P0.idx
  T-mid   = (P0.idx + P3.idx) / 2

Time-asymmetry bias (Hurst's third law):
  P1.idx > T-mid  → rally took longer than correction → BULLISH trend bias
  P1.idx < T-mid  → rally was fast, correction slow → BEARISH (countertrend)
  P1.idx == T-mid → neutral

Trade emission (per H29 brief, "resolved ambiguities" — choices live here so
future agents know what was *spec'd* vs what was *chosen*):
  1. Swing detection: scipy.signal.find_peaks. Spec said "same prominence/
     distance as patterns.py M-pattern detector." That detector uses
     prominence=3.0 in RSI units (0–100 bounded) and distance=3 bars; applied
     literally to *price* the prominence is degenerate (DXY ~100 → 3-unit
     swings exist; EURUSD ~1.05 → 3-unit swings NEVER exist). Chosen:
     distance=3 bars (preserved); prominence as a *fraction of price*
     (PROMINENCE_FRAC default 0.005 = 0.5% of close) — price-normalized so
     swings are detected with the same selectivity across symbols, which is
     the *spirit* of the spec, not the dead letter.
  2. First-touch rule for P2 and P3 — used as written.
  3. Dedup: once a box completes at P3, no new box starts with the same P0.
     The next valid P0 must be a new swing low (LONG) or high (SHORT)
     discovered strictly AFTER P3.
  4. Entry: CLOSE of bar (P3.idx + 1). If P3 is the last bar, drop the box.
  5. Stop: P2 low (LONG) / P2 high (SHORT) — the structural invalidation.
  6. Targets: SURF Fib 1.618 / 2.236 / 3.618 × range where
                range = (P1 − P2) for LONG, mirrored for SHORT.
     Trail: 3-bar at 3.600× range (reusing position_sizing.simulate_fib_trade).
  7. Bias filter: take the trade ONLY if the time-asymmetry verdict MATCHES
     the box direction (LONG box + BULLISH → trade; LONG box + BEARISH →
     skip the countertrend; SHORT box mirrored).

Pure-numpy core (`detect_box_numpy`) + pandas wrapper (`detect_boxes_df`).
Detection is O(n): swing extrema enumerated once via find_peaks; the box
walk advances monotonically (no nested loop replays bars).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from . import position_sizing as ps

PROMINENCE_FRAC: float = 0.005      # 0.5% of price (see ambiguity #1)
DISTANCE_BARS: int = 3              # same as M-detector
FIB_LEVELS = (1.618, 2.236, 3.618)


@dataclass(frozen=True)
class BoxPattern:
    direction: Literal["long", "short"]
    p0_idx: int
    p0_price: float
    p1_idx: int
    p1_price: float
    p2_idx: int
    p2_price: float
    p3_idx: int
    p3_price: float          # the first price > P1 (LONG) or < P1 (SHORT) — used only for plotting
    height: float
    length: int
    t_mid: float
    asymmetry: Literal["bullish", "bearish", "neutral"]
    trade_aligned: bool      # asymmetry matches box direction → take the trade


# ---------------------------------------------------------------------------
# Pure-numpy detector
# ---------------------------------------------------------------------------

def _swings(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    *,
    prominence_frac: float = PROMINENCE_FRAC,
    distance: int = DISTANCE_BARS,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (trough_indices, peak_indices) on the close series with a
    price-normalized prominence. Distance is in bars (preserved from
    M-detector). Empty arrays if the series is too short."""
    n = len(closes)
    if n < 2 * distance + 1:
        return np.array([], dtype=int), np.array([], dtype=int)
    prom = float(prominence_frac) * float(np.median(closes))
    peak_idx, _ = find_peaks(closes, prominence=prom, distance=distance)
    trough_idx, _ = find_peaks(-closes, prominence=prom, distance=distance)
    return trough_idx.astype(int), peak_idx.astype(int)


def detect_box_numpy(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    direction: Literal["long", "short"],
    *,
    prominence_frac: float = PROMINENCE_FRAC,
    distance: int = DISTANCE_BARS,
) -> list[BoxPattern]:
    """One-pass box detector. ``direction='long'`` → P0=trough, P1=peak;
    ``direction='short'`` → P0=peak, P1=trough. Operates on pure numpy."""
    n = len(closes)
    if n < 2 * distance + 1:
        return []
    trough_idx, peak_idx = _swings(closes, highs, lows,
                                   prominence_frac=prominence_frac,
                                   distance=distance)
    boxes: list[BoxPattern] = []

    if direction == "long":
        p0_pool = trough_idx
        p1_pool = peak_idx
        p0_prices = lows           # P0 anchored on the LOW of the trough bar
        p1_prices = highs          # P1 anchored on the HIGH of the peak bar
    else:
        p0_pool = peak_idx
        p1_pool = trough_idx
        p0_prices = highs
        p1_prices = lows

    last_p3 = -1
    for p0 in p0_pool:
        if p0 <= last_p3:
            continue                # dedup rule (#3): need a new P0 after P3
        # P1 = first p1 in p1_pool AFTER p0
        next_p1 = p1_pool[p1_pool > p0]
        if len(next_p1) == 0:
            continue
        p1 = int(next_p1[0])
        p0p = float(p0_prices[p0])
        p1p = float(p1_prices[p1])
        if direction == "long":
            if p1p <= p0p:          # height must be positive
                continue
            mid_level = p0p + 0.5 * (p1p - p0p)
        else:
            if p1p >= p0p:
                continue
            mid_level = p0p + 0.5 * (p1p - p0p)   # = p0p − 0.5·|height|

        # P2 = first bar AFTER p1 whose extreme crosses the 50% level
        p2: Optional[int] = None
        for i in range(p1 + 1, n):
            if direction == "long":
                if lows[i] <= mid_level:
                    p2 = i; break
            else:
                if highs[i] >= mid_level:
                    p2 = i; break
        if p2 is None:
            continue

        # P3 = first bar AFTER p2 whose extreme exceeds p1
        p3: Optional[int] = None
        for j in range(p2 + 1, n):
            if direction == "long":
                if highs[j] > p1p:
                    p3 = j; break
            else:
                if lows[j] < p1p:
                    p3 = j; break
        if p3 is None:
            continue

        height = abs(p1p - p0p)
        length = p3 - p0
        t_mid = (p0 + p3) / 2.0
        if p1 > t_mid:
            asymmetry: Literal["bullish", "bearish", "neutral"] = "bullish"
        elif p1 < t_mid:
            asymmetry = "bearish"
        else:
            asymmetry = "neutral"
        trade_aligned = (direction == "long" and asymmetry == "bullish") or \
                        (direction == "short" and asymmetry == "bearish")

        p2_price = float(lows[p2] if direction == "long" else highs[p2])
        p3_price = float(highs[p3] if direction == "long" else lows[p3])

        boxes.append(BoxPattern(
            direction=direction, p0_idx=int(p0), p0_price=p0p,
            p1_idx=int(p1), p1_price=p1p,
            p2_idx=int(p2), p2_price=p2_price,
            p3_idx=int(p3), p3_price=p3_price,
            height=height, length=length, t_mid=t_mid,
            asymmetry=asymmetry, trade_aligned=trade_aligned,
        ))
        last_p3 = p3
    return boxes


# ---------------------------------------------------------------------------
# pandas wrapper
# ---------------------------------------------------------------------------

def detect_boxes_df(
    df: pd.DataFrame,
    direction: Literal["long", "short"] = "long",
    *,
    prominence_frac: float = PROMINENCE_FRAC,
    distance: int = DISTANCE_BARS,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> list[BoxPattern]:
    return detect_box_numpy(
        df[high_col].to_numpy(), df[low_col].to_numpy(),
        df[close_col].to_numpy(), direction=direction,
        prominence_frac=prominence_frac, distance=distance,
    )


# ---------------------------------------------------------------------------
# Box → FibTrade (uses position_sizing.simulate_fib_trade)
# ---------------------------------------------------------------------------

def box_to_trade(
    box: BoxPattern,
    df: pd.DataFrame,
    *,
    bias_filter: bool = True,
    max_bars: int = 200,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> Optional[ps.FibTrade]:
    """Convert a confirmed box into a simulated FibTrade. Returns None if
    the bias filter (#7) rejects the box, or if entry/stop are degenerate."""
    if bias_filter and not box.trade_aligned:
        return None
    n = len(df)
    entry_idx = box.p3_idx + 1
    if entry_idx >= n:
        return None
    entry_price = float(df[close_col].iloc[entry_idx])
    if box.direction == "long":
        initial_stop = float(df[low_col].iloc[box.p2_idx])
        if initial_stop >= entry_price:
            return None
        range_size = box.p1_price - initial_stop
        if range_size <= 0:
            return None
        targets = [entry_price + lvl * range_size for lvl in FIB_LEVELS]
        trade = ps.FibTrade(
            direction="long", entry_idx=entry_idx, entry_price=entry_price,
            range_size=range_size, range_high_idx=box.p1_idx,
            range_low_idx=box.p2_idx, initial_stop=initial_stop,
            targets=targets,
        )
    else:
        initial_stop = float(df[high_col].iloc[box.p2_idx])
        if initial_stop <= entry_price:
            return None
        range_size = initial_stop - box.p1_price
        if range_size <= 0:
            return None
        targets = [entry_price - lvl * range_size for lvl in FIB_LEVELS]
        trade = ps.FibTrade(
            direction="short", entry_idx=entry_idx, entry_price=entry_price,
            range_size=range_size, range_high_idx=box.p2_idx,
            range_low_idx=box.p1_idx, initial_stop=initial_stop,
            targets=targets,
        )
    return ps.simulate_fib_trade(df, trade, max_bars=max_bars,
                                  close_col=close_col, high_col=high_col,
                                  low_col=low_col)
