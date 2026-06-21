"""Box-pattern signal — Dr. A's 4-point swing structure + Hurst time-asymmetry bias.

H30 CORRECTED SPEC (2026-06-20) — supersedes H29 defaults. H29 had two
material errors flagged by Dr. A; both are fixed here with the H30 values
as the defaults, while the H29 behaviour remains addressable via
parameters so prior results stay reproducible.

  ERROR #1 — T1/2 endpoint. H29 used T-mid = (P0 + P3)/2, which contaminates
  the translation read with the breakout-phase length (P2→P3). The correct
  endpoint is P2: translation should compare *rally vs correction*, not
  rally vs (correction + breakout). Corrected: T-mid = (P0 + P2)/2 by
  default; pass ``t_endpoint='p3'`` for the legacy H29 read.

  ERROR #2 — strict confirmation gate. The H29 "trade_aligned" filter just
  required (direction == translation_verdict). The H30 gate also requires
  the direction's actual breakout to match — i.e. for a LONG to confirm
  P1 must be RIGHT of corrected T1/2 *and* P3 must break ABOVE P1; for a
  SHORT, P1 LEFT *and* P3 breaks BELOW P1. The detector already enforces
  the breakout side per direction, so this gate is reflected in
  ``trade_aligned`` using the corrected T-mid.

  Detector bound: ``max_length`` (default 250 bars) caps the length P3−P0
  to prevent the "mega-box" artifact H29's visualization surfaced (the
  1024-bar 2022→2026 DXY SHORT box). Boxes whose length exceeds the cap
  are dropped pre-confirmation.

Spec (LONG box; SHORT box mirrors):
  P0  swing LOW
  P1  subsequent swing HIGH (after P0)
  P2  first bar whose LOW ≤ midpoint(P0,P1) = P0 + 0.5·(P1 − P0)
      → "box pre-condition" established (need NOT break below P0)
  P3  first bar AFTER P2 whose HIGH > P1.high → "box confirmed"
  Height  = P1.price − P0.price                       (price magnitude)
  Length  = P3.idx − P0.idx                           (bars)
  T-mid   = (P0.idx + P2.idx) / 2                     (corrected H30 default)

Time-asymmetry bias (Hurst's third law):
  P1.idx > T-mid  → rally took longer than correction → BULLISH trend bias
  P1.idx < T-mid  → rally was fast, correction slow → BEARISH (countertrend)
  P1.idx == T-mid → neutral

Target rules — two variants tested side-by-side:
  VARIANT A (Dr. A's H30 primary, tightened 2026-06-20): TWO targets,
    1.618 / 2.236 × height, projected from P2 in the breakout direction.
      LONG  target_k = P2_price + level_k · height
      SHORT target_k = P2_price − level_k · height
    Trail activates *near the final target* — for A that means near T2_A
    = P2 ± 2.236·height. The factor (TRAIL_ACTIVATION_FRAC_A = 2.200)
    mirrors B's "3.600 near 3.618" convention but is anchored on P2
    (not entry), because A's targets are P2-anchored. This is passed
    explicitly to ``simulate_fib_trade`` as ``trail_activation_price``
    so the simulator's default entry-anchored arithmetic doesn't apply.
  VARIANT B (alternative, unchanged): THREE targets, 1.618 / 2.236 /
    3.618 × height, projected from P1; trail factor 3.600 vs entry, same
    convention as M-P1.
      LONG  target_k = P1_price + level_k · height
      SHORT target_k = P1_price − level_k · height

Trade emission (unchanged from H29 except where the corrected spec applies):
  1. Swing detection: scipy.signal.find_peaks. ``distance=3 bars`` (M-detector
     parity); ``prominence`` price-normalized at 0.5% of close because the
     M-detector's prominence=3.0 is in RSI units (0..100) and is degenerate
     on price.
  2. First-touch rule for P2 and P3 — used as written.
  3. Dedup: once a box completes at P3, no new box starts with the same P0.
  4. Entry: CLOSE of bar (P3.idx + 1). If P3 is the last bar, drop the box.
  5. Stop: P2 low (LONG) / P2 high (SHORT) — the structural invalidation.
  6. Targets: see variant A / B above. Trail: 3-bar at 3.600× range, reusing
     ``position_sizing.simulate_fib_trade``; ``range`` for the trail = (P1−P2)
     LONG / (P2−P1) SHORT (the swing magnitude inside the box) — invariant
     across variants so the trail behaves identically regardless of where
     targets are anchored.
  7. Bias filter: take the trade ONLY if asymmetry matches direction (LONG
     box + BULLISH → trade; LONG box + BEARISH → skip the countertrend;
     SHORT box mirrored). H30: this uses the corrected T-mid.

Pure-numpy core (`detect_box_numpy`) + pandas wrapper (`detect_boxes_df`).
Detection is O(n).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from . import position_sizing as ps

PROMINENCE_FRAC: float = 0.005      # 0.5% of price
DISTANCE_BARS: int = 3              # same as M-detector
MAX_LENGTH_BARS: int = 250          # H30: cap to prevent mega-box artifact
FIB_LEVELS_B: tuple[float, float, float] = (1.618, 2.236, 3.618)  # variant B
FIB_LEVELS_A: tuple[float, float] = (1.618, 2.236)                # variant A (H30 tightened 2026-06-20: 2 targets, T3 dropped)
TRAIL_ACTIVATION_FRAC_A: float = 2.200   # near A's T2 = P2 ± 2.236·height (P2-anchored)
TRAIL_ACTIVATION_FRAC_B: float = 3.600   # near B's T3 = entry ± 3.618·range (entry-anchored, M-P1 convention)
FIB_LEVELS = FIB_LEVELS_B   # kept for backwards compatibility with H29 callers

TEndpoint = Literal["p2", "p3"]
TargetVariant = Literal["A", "B"]


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
    t_endpoint: TEndpoint = "p2",
    max_length: Optional[int] = MAX_LENGTH_BARS,
) -> list[BoxPattern]:
    """One-pass box detector. ``direction='long'`` → P0=trough, P1=peak;
    ``direction='short'`` → P0=peak, P1=trough.

    ``t_endpoint`` controls how the translation midpoint is computed:
      * ``"p2"`` (H30 default, corrected): T-mid = (P0 + P2)/2 — measures
        rally vs correction cleanly.
      * ``"p3"`` (H29 legacy): T-mid = (P0 + P3)/2 — contaminated by the
        breakout phase, kept available so H29 results stay reproducible.

    ``max_length`` (in bars, P3 − P0) drops boxes longer than the cap to
    prevent the "mega-box" artifact (the 1024-bar 2022→2026 DXY case).
    Pass ``None`` to disable.
    """
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
        if max_length is not None and length > max_length:
            # H30 cap: skip the mega-box artifact entirely (no record kept).
            continue
        t_mid = ((p0 + p2) / 2.0) if t_endpoint == "p2" else ((p0 + p3) / 2.0)
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
    t_endpoint: TEndpoint = "p2",
    max_length: Optional[int] = MAX_LENGTH_BARS,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> list[BoxPattern]:
    return detect_box_numpy(
        df[high_col].to_numpy(), df[low_col].to_numpy(),
        df[close_col].to_numpy(), direction=direction,
        prominence_frac=prominence_frac, distance=distance,
        t_endpoint=t_endpoint, max_length=max_length,
    )


# ---------------------------------------------------------------------------
# Box → FibTrade (uses position_sizing.simulate_fib_trade)
# ---------------------------------------------------------------------------

def _targets_for(box: BoxPattern, target_variant: TargetVariant,
                  entry_price: float) -> list[float]:
    """Compute target prices per the H30 variants.

    * VARIANT A (Dr. A's primary, tightened 2026-06-20): TWO targets, 1.618
      and 2.236 × ``box.height``, projected from ``box.p2_price`` in the
      breakout direction. T3 dropped.
    * VARIANT B (alternative): THREE targets, 1.618 / 2.236 / 3.618 ×
      ``box.height``, projected from ``box.p1_price`` in the breakout
      direction.

    ``entry_price`` is accepted for legacy/general-purpose fallback semantics
    but is NOT used by either H30 variant — both anchor on box geometry.
    """
    levels = FIB_LEVELS_A if target_variant == "A" else FIB_LEVELS_B
    anchor = box.p2_price if target_variant == "A" else box.p1_price
    sign = +1.0 if box.direction == "long" else -1.0
    return [anchor + sign * lvl * box.height for lvl in levels]


def _trail_activation_price_for(box: BoxPattern, target_variant: TargetVariant,
                                 entry_price: float, range_size: float) -> float:
    """Trail activates near the final target for each variant.

    Variant A targets are anchored on P2; "near the final target" therefore
    means ``P2 ± TRAIL_ACTIVATION_FRAC_A · height`` (mirror of B's
    "3.600 near 3.618"). We pass this explicitly because the simulator's
    default trail-price computation is entry-anchored.

    Variant B keeps the M-P1 convention: trail near 3.600 × range from
    entry. ``range_size`` here is the simulator's trail range (= box height
    in the current box_to_trade impl).
    """
    sign = +1.0 if box.direction == "long" else -1.0
    if target_variant == "A":
        return box.p2_price + sign * TRAIL_ACTIVATION_FRAC_A * box.height
    return entry_price + sign * TRAIL_ACTIVATION_FRAC_B * range_size


def box_to_trade(
    box: BoxPattern,
    df: pd.DataFrame,
    *,
    bias_filter: bool = True,
    target_variant: TargetVariant = "A",
    max_bars: int = 200,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> Optional[ps.FibTrade]:
    """Convert a confirmed box into a simulated FibTrade. Returns ``None`` if
    the bias filter (#7) rejects the box, or if entry/stop are degenerate.

    ``target_variant`` selects the H30 target-ladder spec (default "A" is the
    Dr.-A primary). Stop, entry, and trail-activation range are unchanged
    across variants; only the T1/T2/T3 prices differ."""
    if bias_filter and not box.trade_aligned:
        return None
    n = len(df)
    entry_idx = box.p3_idx + 1
    if entry_idx >= n:
        return None
    entry_price = float(df[close_col].iloc[entry_idx])
    targets = _targets_for(box, target_variant, entry_price)
    if box.direction == "long":
        initial_stop = float(df[low_col].iloc[box.p2_idx])
        if initial_stop >= entry_price:
            return None
        range_size = box.p1_price - initial_stop
        if range_size <= 0:
            return None
        # Targets must be ABOVE entry for a long; otherwise the trade is
        # degenerate (anchor-from-P2 with a tiny height could in principle
        # land below the entry close — drop it then).
        if targets[0] <= entry_price:
            return None
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
        if targets[0] >= entry_price:
            return None
        trade = ps.FibTrade(
            direction="short", entry_idx=entry_idx, entry_price=entry_price,
            range_size=range_size, range_high_idx=box.p2_idx,
            range_low_idx=box.p1_idx, initial_stop=initial_stop,
            targets=targets,
        )
    trail_price = _trail_activation_price_for(box, target_variant,
                                               entry_price, range_size)
    return ps.simulate_fib_trade(df, trade, max_bars=max_bars,
                                  trail_activation_price=trail_price,
                                  close_col=close_col, high_col=high_col,
                                  low_col=low_col)
