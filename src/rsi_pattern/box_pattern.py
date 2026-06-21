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

from dataclasses import dataclass, replace as _replace
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
    # Chain extension (H30c, 2026-06-20). Populated only by `chain_mode=True`
    # detection; standalone runs leave these None.
    chain_id: Optional[int] = None          # monotonic chain identifier
    chain_index: Optional[int] = None       # 0 = first box of chain, 1 = first continuation, ...
    reverses_chain_id: Optional[int] = None # if this box reversed a prior chain, that chain's id


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
    legacy: bool = False,
    chain_mode: bool = False,
) -> list[BoxPattern]:
    """One-pass box detector. ``direction='long'`` → P0=trough, P1=peak;
    ``direction='short'`` → P0=peak, P1=trough.

    ``chain_mode=True`` (H30c) returns ALL boxes (both directions) in
    chain order, each annotated with ``chain_id`` / ``chain_index`` /
    ``reverses_chain_id``. After a box confirms, a continuation candidate
    (P0 = previous P2, same direction) and a reversal candidate (P0 = the
    chain's running terminal extreme, opposite direction) are raced; the
    first to confirm a P3 wins and either extends the chain (continuation)
    or ends it and starts a new opposite-direction chain (reversal). The
    ``direction`` parameter is used ONLY to choose the very first seed
    direction; the returned list mixes long and short boxes naturally.

    H30b (2026-06-20, this revision) — **corrected P1 algorithm**.

    The legacy detector (H29 / H30a) nominated P1 from a pre-computed
    ``find_peaks`` list, locking it at the FIRST local extremum after P0.
    On a dominant impulse with intermediate prominent peaks (e.g. the 2008
    DXY rally: P0 ≈ 75.7 in Sep '08, first local peak ≈ 82 early Oct '08,
    dominant peak ≈ 88 late Oct '08), the legacy code locked P1 at 82 and
    ran the rest of the geometry off the wrong opposite swing.

    Corrected algorithm: walk forward from each candidate P0, maintaining a
    running extreme (max-high for LONG, min-low for SHORT). P1 only locks
    when the first 50%-retracement bar fires the box pre-condition, at
    which moment P1 = (running_extreme_idx, running_extreme_price). This
    lets P1 extend with the impulse until the impulse demonstrably ends.
    Concurrent P0 candidates are tracked; an invalidating extreme
    (low < P0_price for LONG, etc.) drops the candidate and respawns one
    at the current bar; the first candidate to trigger AND complete (P3
    found within max_length) wins, with later in-box candidates dropped
    for dedup.

    ``legacy=True`` restores the H29/H30a behaviour for reproducibility.

    ``t_endpoint`` controls how the translation midpoint is computed:
      * ``"p2"`` (H30 default, corrected): T-mid = (P0 + P2)/2.
      * ``"p3"`` (H29 legacy): T-mid = (P0 + P3)/2.

    ``max_length`` (bars, P3 − P0) drops boxes longer than the cap and
    additionally abandons P0 candidates whose impulse phase exceeds it.
    Pass ``None`` to disable.
    """
    if chain_mode:
        return _detect_box_chained(highs, lows, closes,
                                    prominence_frac=prominence_frac,
                                    distance=distance,
                                    t_endpoint=t_endpoint,
                                    max_length=max_length)
    if legacy:
        return _detect_box_legacy(highs, lows, closes, direction,
                                   prominence_frac=prominence_frac,
                                   distance=distance,
                                   t_endpoint=t_endpoint,
                                   max_length=max_length)
    return _detect_box_corrected(highs, lows, closes, direction,
                                  prominence_frac=prominence_frac,
                                  distance=distance,
                                  t_endpoint=t_endpoint,
                                  max_length=max_length)


# ---------------------------------------------------------------------------
# Corrected detector (H30b)
# ---------------------------------------------------------------------------

def _detect_box_corrected(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    direction: Literal["long", "short"],
    *,
    prominence_frac: float,
    distance: int,
    t_endpoint: TEndpoint,
    max_length: Optional[int],
) -> list[BoxPattern]:
    """Single-candidate-at-a-time implementation.

    Design choice (load-bearing, vs the brief's "concurrent candidates,
    first to trigger wins" simplest-impl suggestion): we prefer the EARLIEST
    candidate. Concurrent candidates from intermediate ``find_peaks``-
    identified troughs are NOT spawned while an active candidate is running
    its impulse — they would otherwise trigger earlier (with a higher
    retrace level relative to their later P0) and steal the box from the
    deeper, structurally meaningful P0. That is exactly the failure mode
    Dr. A's 2008 DXY example calls out (P0 = Sep '08 swing low, dominant
    peak ~88), and matches his stated intent: "P1 must be the highest
    high reached between P0 and the bar where price first retraces 50% of
    the running impulse."

    New P0 candidates only spawn (a) at find_peaks-identified troughs strictly
    after the current candidate is dropped (invalidation, abandonment, or
    box completion at P3); or (b) at the bar where invalidation fires
    (low < P0_price for LONG, mirror for SHORT) — the new lower low
    becomes the next P0 immediately.
    """
    n = len(closes)
    if n < 2 * distance + 1:
        return []
    trough_idx, peak_idx = _swings(closes, highs, lows,
                                   prominence_frac=prominence_frac,
                                   distance=distance)
    cap = max_length if max_length is not None else 10**9

    if direction == "long":
        p0_seed = sorted(int(x) for x in trough_idx)
        def p0_price_at(i): return float(lows[i])
        def running_at(i):  return float(highs[i])
        def is_better(new, cur): return new > cur
        def retrace(p0p, re): return re - 0.5 * (re - p0p)
        def retrace_hit(i, level): return lows[i] <= level
        def invalidated(i, p0p): return lows[i] < p0p
        def p2_price_at(i): return float(lows[i])
        def p3_price_at(j): return float(highs[j])
        def find_p3(p0i, start, p1p):
            end = min(n, p0i + cap + 1)
            for j in range(start, end):
                if highs[j] > p1p:
                    return j
            return None
    else:
        p0_seed = sorted(int(x) for x in peak_idx)
        def p0_price_at(i): return float(highs[i])
        def running_at(i):  return float(lows[i])
        def is_better(new, cur): return new < cur
        def retrace(p0p, re): return re + 0.5 * (p0p - re)
        def retrace_hit(i, level): return highs[i] >= level
        def invalidated(i, p0p): return highs[i] > p0p
        def p2_price_at(i): return float(highs[i])
        def p3_price_at(j): return float(lows[j])
        def find_p3(p0i, start, p1p):
            end = min(n, p0i + cap + 1)
            for j in range(start, end):
                if lows[j] < p1p:
                    return j
            return None

    boxes: list[BoxPattern] = []
    last_p3 = -1

    def next_seed_after(idx: int) -> Optional[int]:
        for s in p0_seed:
            if s > idx:
                return s
        return None

    def emit_box(p0_idx: int, p0p: float, p1_idx: int, p1p: float,
                  p2_idx: int, p3_idx: int) -> bool:
        length = p3_idx - p0_idx
        if length > cap:
            return False
        height = abs(p1p - p0p)
        if height <= 0:
            return False
        p2p = p2_price_at(p2_idx)
        t_mid = ((p0_idx + p2_idx) / 2.0) if t_endpoint == "p2" \
                else ((p0_idx + p3_idx) / 2.0)
        if p1_idx > t_mid:
            asym: Literal["bullish", "bearish", "neutral"] = "bullish"
        elif p1_idx < t_mid:
            asym = "bearish"
        else:
            asym = "neutral"
        aligned = (
            (direction == "long" and asym == "bullish") or
            (direction == "short" and asym == "bearish")
        )
        # H30d Bug 1 fix: p3_price stores P1's level (the threshold the
        # bar crossed), NOT the bar's own actual high/low. Renderers using
        # box.p3_price as the marker y-coordinate now sit at P1's level,
        # matching Dr. A's intent ("Point-3 level always is equal to
        # point-1 level"). The bar's actual high/low at P3 is recoverable
        # from the source data if needed.
        boxes.append(BoxPattern(
            direction=direction,
            p0_idx=int(p0_idx), p0_price=p0p,
            p1_idx=int(p1_idx), p1_price=p1p,
            p2_idx=int(p2_idx), p2_price=p2p,
            p3_idx=int(p3_idx), p3_price=p1p,
            height=height, length=length, t_mid=t_mid,
            asymmetry=asym, trade_aligned=aligned,
        ))
        return True

    # Start scanning from the first find_peaks trough/peak after last_p3.
    cand_p0_idx: Optional[int] = next_seed_after(last_p3)
    while cand_p0_idx is not None and cand_p0_idx < n:
        p0_idx = cand_p0_idx
        p0p = p0_price_at(p0_idx)
        re_idx = p0_idx
        re_price = running_at(p0_idx)
        # H30d (2026-06-20) — gate the 50% retrace on running_max having
        # ACTUALLY moved past P0's running value. Without this gate the
        # detector collapses to P1==P0 on bars where no post-P0 high
        # exceeded P0's high — producing 1-bar micro-boxes whose "swing"
        # is just the P0 bar's intra-bar range (Dr. A's "box shallower
        # than price action" complaint).
        re_updated = False
        triggered = False
        respawned: Optional[int] = None
        i = p0_idx + 1
        while i < n:
            if (i - p0_idx) > cap:
                break  # abandon, look for next seed past this candidate
            current = running_at(i)
            if is_better(current, re_price):
                re_price = current
                re_idx = i
                re_updated = True
                i += 1
                continue
            # Invalidation check FIRST (per spec wording: "before the 50% retrace triggers")
            if invalidated(i, p0p):
                respawned = i  # respawn at this bar (new lower low / higher high)
                break
            # 50% retrace check — gated on re_updated (Bug 2 fix)
            if re_updated:
                level = retrace(p0p, re_price)
                if retrace_hit(i, level):
                    p3_idx = find_p3(p0_idx, i + 1, re_price)
                    if p3_idx is None:
                        # No P3 within cap → abandon
                        break
                    if emit_box(p0_idx, p0p, re_idx, re_price, i, p3_idx):
                        last_p3 = p3_idx
                        triggered = True
                    # In either case (emit OR cap-reject) this candidate is done.
                    break
            i += 1

        # Decide next candidate
        if triggered:
            cand_p0_idx = next_seed_after(last_p3)
        elif respawned is not None:
            # New P0 immediately at the invalidation bar
            cand_p0_idx = respawned
        else:
            # Abandoned (no trigger, no invalidation) — try next find_peaks seed
            cand_p0_idx = next_seed_after(p0_idx)
    return boxes


# ---------------------------------------------------------------------------
# Direction-polymorphic helpers (used by the chained detector)
# ---------------------------------------------------------------------------

def _running_at(direction: str, highs: np.ndarray, lows: np.ndarray, i: int) -> float:
    return float(highs[i]) if direction == "long" else float(lows[i])


def _is_better(direction: str, new: float, cur: float) -> bool:
    return new > cur if direction == "long" else new < cur


def _p0_price_at(direction: str, highs: np.ndarray, lows: np.ndarray, i: int) -> float:
    return float(lows[i]) if direction == "long" else float(highs[i])


def _p2_price_at(direction: str, highs: np.ndarray, lows: np.ndarray, i: int) -> float:
    return float(lows[i]) if direction == "long" else float(highs[i])


def _p3_price_at(direction: str, highs: np.ndarray, lows: np.ndarray, j: int) -> float:
    return float(highs[j]) if direction == "long" else float(lows[j])


def _invalidates(direction: str, highs: np.ndarray, lows: np.ndarray,
                 i: int, p0_price: float) -> bool:
    return lows[i] < p0_price if direction == "long" else highs[i] > p0_price


def _retrace_level(direction: str, p0_price: float, re_price: float) -> float:
    if direction == "long":
        return re_price - 0.5 * (re_price - p0_price)
    return re_price + 0.5 * (p0_price - re_price)


def _retrace_hit(direction: str, highs: np.ndarray, lows: np.ndarray,
                 i: int, level: float) -> bool:
    return lows[i] <= level if direction == "long" else highs[i] >= level


def _find_p3(direction: str, highs: np.ndarray, lows: np.ndarray,
             p0_idx: int, start: int, p1_price: float, cap: int, n: int
             ) -> Optional[int]:
    end = min(n, p0_idx + cap + 1)
    if direction == "long":
        for j in range(start, end):
            if highs[j] > p1_price:
                return j
    else:
        for j in range(start, end):
            if lows[j] < p1_price:
                return j
    return None


def _build_box(direction: str, p0_idx: int, p0_price: float,
               p1_idx: int, p1_price: float,
               p2_idx: int, p2_price: float, p3_idx: int, p3_price: float,
               *, t_endpoint: TEndpoint, cap: int) -> Optional[BoxPattern]:
    length = p3_idx - p0_idx
    if length > cap:
        return None
    height = abs(p1_price - p0_price)
    if height <= 0:
        return None
    t_mid = ((p0_idx + p2_idx) / 2.0) if t_endpoint == "p2" \
            else ((p0_idx + p3_idx) / 2.0)
    if p1_idx > t_mid:
        asym: Literal["bullish", "bearish", "neutral"] = "bullish"
    elif p1_idx < t_mid:
        asym = "bearish"
    else:
        asym = "neutral"
    aligned = (
        (direction == "long" and asym == "bullish") or
        (direction == "short" and asym == "bearish")
    )
    # H30d Bug 1 fix: see emit_box in _detect_box_corrected — p3_price is
    # P1's level (the threshold the breakout bar crossed), not the bar's
    # own actual high/low. The caller's p3_price argument is ignored for
    # the same reason on this corrected path.
    return BoxPattern(
        direction=direction,
        p0_idx=int(p0_idx), p0_price=p0_price,
        p1_idx=int(p1_idx), p1_price=p1_price,
        p2_idx=int(p2_idx), p2_price=p2_price,
        p3_idx=int(p3_idx), p3_price=p1_price,
        height=height, length=length, t_mid=t_mid,
        asymmetry=asym, trade_aligned=aligned,
    )


# ---------------------------------------------------------------------------
# Chained detector (H30c) — continuation + reversal racing
# ---------------------------------------------------------------------------

def _walk_first_box(highs: np.ndarray, lows: np.ndarray,
                     p0_idx: int, direction: str, cap: int,
                     t_endpoint: TEndpoint, n: int
                     ) -> Optional[BoxPattern]:
    """Run the single-candidate walk from one P0 seed. Returns the first
    confirmed box, or None if abandoned/invalidated without confirming."""
    p0_price = _p0_price_at(direction, highs, lows, p0_idx)
    re_idx = p0_idx
    re_price = _running_at(direction, highs, lows, p0_idx)
    re_updated = False  # H30d: gate retrace on running_max actually advancing past P0
    i = p0_idx + 1
    while i < n:
        if (i - p0_idx) > cap:
            return None
        current = _running_at(direction, highs, lows, i)
        if _is_better(direction, current, re_price):
            re_price = current
            re_idx = i
            re_updated = True
            i += 1
            continue
        if _invalidates(direction, highs, lows, i, p0_price):
            return None  # caller should respawn from next seed (cleaner here)
        if re_updated:
            level = _retrace_level(direction, p0_price, re_price)
            if _retrace_hit(direction, highs, lows, i, level):
                p3 = _find_p3(direction, highs, lows, p0_idx, i + 1, re_price, cap, n)
                if p3 is None:
                    return None
                p2_price = _p2_price_at(direction, highs, lows, i)
                p3_price = _p3_price_at(direction, highs, lows, p3)
                return _build_box(direction, p0_idx, p0_price, re_idx, re_price,
                                  i, p2_price, p3, p3_price,
                                  t_endpoint=t_endpoint, cap=cap)
        i += 1
    return None


def _walk_chain_continuation(
    highs: np.ndarray, lows: np.ndarray,
    current_box: BoxPattern,
    chain_direction: str,
    chain_terminal_idx: int,
    chain_terminal_price: float,
    start_bar: int,
    cap: int,
    t_endpoint: TEndpoint,
    n: int,
) -> tuple[Optional[BoxPattern], Optional[str], int, float]:
    """Race the continuation candidate (P0 = current_box.P2, same direction)
    against the reversal candidate (P0 = chain's running terminal extreme,
    opposite direction). Returns (next_box, type, new_terminal_idx,
    new_terminal_price). type ∈ {"cont", "rev"} or None if both abandoned.
    """
    cont_dir = chain_direction
    rev_dir = "short" if cont_dir == "long" else "long"

    cont_p0 = current_box.p2_idx
    cont_p0_price = current_box.p2_price
    cont_re_idx = cont_p0
    cont_re_price = _running_at(cont_dir, highs, lows, cont_p0)
    cont_re_updated = False    # H30d gate (see _detect_box_corrected)

    rev_p0_idx = chain_terminal_idx
    rev_p0_price = chain_terminal_price
    rev_re_idx = rev_p0_idx
    rev_re_price = _running_at(rev_dir, highs, lows, rev_p0_idx)
    rev_re_updated = False     # H30d gate

    term_idx = chain_terminal_idx
    term_price = chain_terminal_price

    j = start_bar
    while j < n:
        cont_alive = (j - cont_p0) <= cap
        rev_alive = (j - rev_p0_idx) <= cap
        if not cont_alive and not rev_alive:
            return None, None, term_idx, term_price

        # Update chain terminal extreme (in chain direction)
        cur_chain = _running_at(cont_dir, highs, lows, j)
        if _is_better(cont_dir, cur_chain, term_price):
            term_price = cur_chain
            term_idx = j
            # Reversal P0 follows the chain terminal: respawn rev candidate
            rev_p0_idx = j
            rev_p0_price = cur_chain
            rev_re_idx = j
            rev_re_price = _running_at(rev_dir, highs, lows, j)
            rev_re_updated = False  # H30d: respawned candidate hasn't earned an update yet

        # ---- Continuation track update ----
        if cont_alive:
            cur_cont = _running_at(cont_dir, highs, lows, j)
            if _is_better(cont_dir, cur_cont, cont_re_price):
                cont_re_price = cur_cont
                cont_re_idx = j
                cont_re_updated = True
            else:
                if _invalidates(cont_dir, highs, lows, j, cont_p0_price):
                    # Respawn cont at this bar
                    cont_p0 = j
                    cont_p0_price = _p0_price_at(cont_dir, highs, lows, j)
                    cont_re_idx = j
                    cont_re_price = _running_at(cont_dir, highs, lows, j)
                    cont_re_updated = False
                elif cont_re_updated:
                    cont_level = _retrace_level(cont_dir, cont_p0_price, cont_re_price)
                    if _retrace_hit(cont_dir, highs, lows, j, cont_level):
                        p3 = _find_p3(cont_dir, highs, lows, cont_p0,
                                      j + 1, cont_re_price, cap, n)
                        if p3 is not None:
                            box = _build_box(cont_dir, cont_p0, cont_p0_price,
                                             cont_re_idx, cont_re_price,
                                             j, _p2_price_at(cont_dir, highs, lows, j),
                                             p3, _p3_price_at(cont_dir, highs, lows, p3),
                                             t_endpoint=t_endpoint, cap=cap)
                            if box is not None:
                                return box, "cont", term_idx, term_price

        # ---- Reversal track update ----
        if rev_alive and j > rev_p0_idx:
            cur_rev = _running_at(rev_dir, highs, lows, j)
            if _is_better(rev_dir, cur_rev, rev_re_price):
                rev_re_price = cur_rev
                rev_re_idx = j
                rev_re_updated = True
            elif rev_re_updated and not _invalidates(rev_dir, highs, lows, j, rev_p0_price):
                # NB: rev invalidation == new chain-direction extreme, which is
                # already handled by the "update chain terminal" block above
                # (it respawns rev_p0 at that bar). So we only get here when
                # the chain terminal didn't move this bar.
                rev_level = _retrace_level(rev_dir, rev_p0_price, rev_re_price)
                if _retrace_hit(rev_dir, highs, lows, j, rev_level):
                    p3 = _find_p3(rev_dir, highs, lows, rev_p0_idx,
                                  j + 1, rev_re_price, cap, n)
                    if p3 is not None:
                        box = _build_box(rev_dir, rev_p0_idx, rev_p0_price,
                                         rev_re_idx, rev_re_price,
                                         j, _p2_price_at(rev_dir, highs, lows, j),
                                         p3, _p3_price_at(rev_dir, highs, lows, p3),
                                         t_endpoint=t_endpoint, cap=cap)
                        if box is not None:
                            return box, "rev", term_idx, term_price
        j += 1
    return None, None, term_idx, term_price


def _detect_box_chained(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    *, prominence_frac: float, distance: int,
    t_endpoint: TEndpoint, max_length: Optional[int],
) -> list[BoxPattern]:
    """Chained detector. Yields boxes annotated with chain_id, chain_index,
    reverses_chain_id. Chains end either by reversal (opposite-direction box
    anchored at the chain's terminal extreme) or silently when neither
    continuation nor reversal confirms within ``max_length`` bars.

    Independent of the ``direction`` parameter on the dispatcher — the
    chained detector returns boxes of BOTH directions (chains can reverse),
    and the dispatcher's ``direction`` is used only to select the initial
    seed pool when scanning the first chain.
    """
    n = len(closes)
    if n < 2 * distance + 1:
        return []
    cap = max_length if max_length is not None else 10**9
    trough_idx, peak_idx = _swings(closes, highs, lows,
                                   prominence_frac=prominence_frac,
                                   distance=distance)
    seeds: list[tuple[int, str]] = sorted(
        [(int(t), "long") for t in trough_idx]
        + [(int(p), "short") for p in peak_idx]
    )

    out: list[BoxPattern] = []
    next_chain_id = 0
    seed_pos = 0
    bar = 0
    while bar < n:
        # Find the next seed at or after `bar`
        while seed_pos < len(seeds) and seeds[seed_pos][0] < bar:
            seed_pos += 1
        if seed_pos >= len(seeds):
            break
        seed_bar, init_dir = seeds[seed_pos]

        first = _walk_first_box(highs, lows, seed_bar, init_dir, cap,
                                  t_endpoint=t_endpoint, n=n)
        if first is None:
            seed_pos += 1
            continue

        chain_id = next_chain_id; next_chain_id += 1
        first = _replace(first, chain_id=chain_id, chain_index=0,
                          reverses_chain_id=None)
        out.append(first)

        current = first
        chain_dir = first.direction
        chain_index = 0
        term_idx = first.p1_idx
        term_price = first.p1_price
        # Extend terminal across the breakout to P3
        for k in range(first.p1_idx + 1, first.p3_idx + 1):
            cur = _running_at(chain_dir, highs, lows, k)
            if _is_better(chain_dir, cur, term_price):
                term_price = cur
                term_idx = k

        bar = first.p3_idx + 1
        # Continuation/reversal loop
        while bar < n:
            nbox, ntype, new_term_idx, new_term_price = _walk_chain_continuation(
                highs, lows, current, chain_dir, term_idx, term_price,
                bar, cap, t_endpoint, n
            )
            if nbox is None:
                # Chain ends silently
                break
            if ntype == "cont":
                chain_index += 1
                nbox = _replace(nbox, chain_id=chain_id, chain_index=chain_index,
                                 reverses_chain_id=None)
                out.append(nbox)
                current = nbox
                term_idx = new_term_idx
                term_price = new_term_price
                # Still extend across this new box's breakout to its p3
                for k in range(nbox.p1_idx + 1, nbox.p3_idx + 1):
                    cur = _running_at(chain_dir, highs, lows, k)
                    if _is_better(chain_dir, cur, term_price):
                        term_price = cur
                        term_idx = k
                bar = nbox.p3_idx + 1
            else:
                # Reversal: end this chain, start a new one
                old_chain_id = chain_id
                chain_id = next_chain_id; next_chain_id += 1
                nbox = _replace(nbox, chain_id=chain_id, chain_index=0,
                                 reverses_chain_id=old_chain_id)
                out.append(nbox)
                current = nbox
                chain_dir = nbox.direction
                chain_index = 0
                term_idx = nbox.p1_idx
                term_price = nbox.p1_price
                for k in range(nbox.p1_idx + 1, nbox.p3_idx + 1):
                    cur = _running_at(chain_dir, highs, lows, k)
                    if _is_better(chain_dir, cur, term_price):
                        term_price = cur
                        term_idx = k
                bar = nbox.p3_idx + 1
        # Advance seed_pos past current bar for the NEXT outer chain start
        while seed_pos < len(seeds) and seeds[seed_pos][0] < bar:
            seed_pos += 1
    return out


# ---------------------------------------------------------------------------
# Legacy detector (H29 / H30a) — preserved for reproducibility (`legacy=True`)
# ---------------------------------------------------------------------------

def _detect_box_legacy(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    direction: Literal["long", "short"],
    *,
    prominence_frac: float,
    distance: int,
    t_endpoint: TEndpoint,
    max_length: Optional[int],
) -> list[BoxPattern]:
    n = len(closes)
    if n < 2 * distance + 1:
        return []
    trough_idx, peak_idx = _swings(closes, highs, lows,
                                   prominence_frac=prominence_frac,
                                   distance=distance)
    boxes: list[BoxPattern] = []
    if direction == "long":
        p0_pool = trough_idx; p1_pool = peak_idx
        p0_prices = lows;     p1_prices = highs
    else:
        p0_pool = peak_idx;   p1_pool = trough_idx
        p0_prices = highs;    p1_prices = lows
    last_p3 = -1
    for p0 in p0_pool:
        if p0 <= last_p3:
            continue
        next_p1 = p1_pool[p1_pool > p0]
        if len(next_p1) == 0:
            continue
        p1 = int(next_p1[0])
        p0p = float(p0_prices[p0]); p1p = float(p1_prices[p1])
        if direction == "long":
            if p1p <= p0p:
                continue
            mid_level = p0p + 0.5 * (p1p - p0p)
        else:
            if p1p >= p0p:
                continue
            mid_level = p0p + 0.5 * (p1p - p0p)
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
        height = abs(p1p - p0p); length = p3 - p0
        if max_length is not None and length > max_length:
            continue
        t_mid = ((p0 + p2) / 2.0) if t_endpoint == "p2" else ((p0 + p3) / 2.0)
        if p1 > t_mid:
            asymmetry: Literal["bullish", "bearish", "neutral"] = "bullish"
        elif p1 < t_mid:
            asymmetry = "bearish"
        else:
            asymmetry = "neutral"
        trade_aligned = (
            (direction == "long" and asymmetry == "bullish") or
            (direction == "short" and asymmetry == "bearish")
        )
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
    legacy: bool = False,
    chain_mode: bool = False,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> list[BoxPattern]:
    return detect_box_numpy(
        df[high_col].to_numpy(), df[low_col].to_numpy(),
        df[close_col].to_numpy(), direction=direction,
        prominence_frac=prominence_frac, distance=distance,
        t_endpoint=t_endpoint, max_length=max_length, legacy=legacy,
        chain_mode=chain_mode,
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
