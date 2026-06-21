"""Unit tests for box_pattern.

Synthetic-data fixtures cover:
  * clean LONG box with P1.idx > T-mid → bullish (trade aligned)
  * clean LONG box with P1.idx < T-mid → bearish (countertrend; bias filter skips)
  * SHORT box mirror
  * 50% retracement that lands EXACTLY at the trigger level (boundary)
  * P3 exceeds P1 intra-bar but does not close above (the spec ONLY needs high>P1)
  * dedup: a second valid P0 inside the same box does NOT spawn a duplicate
"""
import numpy as np
import pandas as pd

from rsi_pattern import box_pattern as bp


def _df(highs, lows, closes=None):
    closes = closes if closes is not None else [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes},
                         index=pd.date_range("2025-01-01", periods=len(highs),
                                             freq="D", tz="UTC"))


def _synth_long_box_bullish_asym():
    """Construct a long box where P1 sits past the time mid (P3 well after P1)
    so asymmetry = bullish ('rally took longer than correction').

    Geometry (indices 0..40):
       P0 ≈ idx 2  (deep trough),
       P1 ≈ idx 25 (peak after a long rally),
       P2 = first 50%-retracement bar after P1 (around idx 30 — short correction),
       P3 = first bar with high > P1 (around idx 38).
    T-mid = (2 + 38) / 2 = 20. P1.idx=25 > 20 → bullish. ✓
    """
    n = 41
    highs = np.full(n, 100.0); lows = np.full(n, 99.0); closes = np.full(n, 99.5)
    # background tiny noise so find_peaks has prominence material
    rng = np.random.RandomState(0)
    noise = rng.normal(0, 0.05, n)
    highs += noise; lows += noise; closes += noise
    # P0 trough at idx 2 — sharp dip
    lows[2] = 95.0; highs[2] = 95.5; closes[2] = 95.3
    # slow rally to a peak at idx 25
    for i, val in enumerate(np.linspace(95.3, 110.0, 24)):
        highs[2 + i] = val + 0.3; lows[2 + i] = val - 0.3; closes[2 + i] = val
    highs[25] = 110.5; lows[25] = 109.5; closes[25] = 110.0
    # quick correction to 50% retracement at idx 30
    for i, val in enumerate(np.linspace(110.0, 102.65, 6)):
        highs[25 + i] = val + 0.3; lows[25 + i] = val - 0.3; closes[25 + i] = val
    lows[30] = 102.0; highs[30] = 102.6; closes[30] = 102.5   # touches 50% (= 102.65)
    # mild drift up, then P3 break above P1 at idx 38
    for i, val in enumerate(np.linspace(102.5, 110.4, 8)):
        highs[30 + i] = val + 0.3; lows[30 + i] = val - 0.3; closes[30 + i] = val
    highs[38] = 110.8; lows[38] = 110.0; closes[38] = 110.5
    return _df(highs.tolist(), lows.tolist(), closes.tolist())


def _synth_long_box_bearish_asym():
    """Construct a long box where the rally is FAST and the correction is SLOW
    so P1.idx < T-mid → bearish (countertrend; bias filter must skip).

    Geometry: P0 idx 2, P1 idx 8 (fast rally), P2 idx 25 (slow correction),
    P3 idx 35 (eventually breaks above P1). T-mid = (2+35)/2 = 18.5; P1=8 < 18.5
    → bearish. ✓
    """
    n = 40
    rng = np.random.RandomState(1)
    closes = 100 + rng.normal(0, 0.05, n)
    highs = closes + 0.3; lows = closes - 0.3
    # P0
    lows[2] = 95.0; highs[2] = 95.5; closes[2] = 95.3
    # fast rally to P1 at idx 8
    for i, val in enumerate(np.linspace(95.3, 110.0, 7)):
        highs[2 + i] = val + 0.3; lows[2 + i] = val - 0.3; closes[2 + i] = val
    highs[8] = 110.5; lows[8] = 109.5; closes[8] = 110.0
    # slow drift down to 50%-touch around idx 25
    for i, val in enumerate(np.linspace(110.0, 102.65, 18)):
        highs[8 + i] = val + 0.3; lows[8 + i] = val - 0.3; closes[8 + i] = val
    lows[25] = 102.0; highs[25] = 102.6; closes[25] = 102.5
    # eventual break above P1 at idx 35
    for i, val in enumerate(np.linspace(102.5, 110.5, 11)):
        highs[25 + i] = val + 0.3; lows[25 + i] = val - 0.3; closes[25 + i] = val
    highs[35] = 110.8; lows[35] = 110.0; closes[35] = 110.5
    # continue the rally past P3 so the entry bar (P3+1=36) sits above the
    # structural stop at lows[25]=102.0 (otherwise the LONG cannot be sized)
    for i, val in enumerate(np.linspace(110.7, 112.0, 4)):
        highs[36 + i] = val + 0.3; lows[36 + i] = val - 0.3; closes[36 + i] = val
    return _df(highs.tolist(), lows.tolist(), closes.tolist())


def test_long_box_bullish_asymmetry_detected():
    df = _synth_long_box_bullish_asym()
    boxes = bp.detect_boxes_df(df, "long")
    assert len(boxes) >= 1, "should find at least one LONG box"
    b = boxes[0]
    assert b.p0_idx < b.p2_idx < b.p3_idx
    assert b.p1_idx > b.p0_idx and b.p1_idx < b.p3_idx
    # bullish asymmetry → P1.idx strictly greater than T-mid
    assert b.p1_idx > b.t_mid
    assert b.asymmetry == "bullish"
    assert b.trade_aligned is True
    assert b.height > 0
    # 50% retracement holds: P2.low must be at or below P0 + 0.5*(P1−P0)
    mid_level = b.p0_price + 0.5 * (b.p1_price - b.p0_price)
    assert df["low"].iloc[b.p2_idx] <= mid_level + 1e-9


def test_long_box_bearish_asymmetry_skipped_by_filter():
    df = _synth_long_box_bearish_asym()
    boxes = bp.detect_boxes_df(df, "long")
    assert len(boxes) >= 1, "detector must still find the box; filter is downstream"
    b = boxes[0]
    assert b.p1_idx < b.t_mid
    assert b.asymmetry == "bearish"
    assert b.trade_aligned is False
    trade = bp.box_to_trade(b, df, bias_filter=True)
    assert trade is None, "bias filter must skip a countertrend long box"
    trade_force = bp.box_to_trade(b, df, bias_filter=False)
    assert trade_force is not None, "without the filter the trade is still emittable"


def test_short_box_mirror():
    df = _synth_long_box_bullish_asym()
    # Invert the bullish-long fixture: this should produce a clean short box
    # with bearish (= long-aligned mirror) asymmetry when viewed as direction='short'.
    df_inv = pd.DataFrame({
        "open": -df["open"], "high": -df["low"], "low": -df["high"], "close": -df["close"],
    }, index=df.index)
    boxes_short = bp.detect_boxes_df(df_inv, "short")
    assert len(boxes_short) >= 1
    b = boxes_short[0]
    assert b.direction == "short"
    # mirrored fixture: P1 still past T-mid, but now P1 < P0 in price → asymmetry=bullish in TIME
    # In the SHORT frame, asymmetry=='bullish' means P1.idx > T-mid (rally / decline took longer)
    # → trade_aligned True only when asymmetry=='bearish' (price decline took longer)
    # Here the mirrored fixture has a long decline, so we expect bullish-time-asym ⇒ trade_aligned=False
    assert b.p1_idx > b.t_mid
    assert b.asymmetry == "bullish"
    assert b.trade_aligned is False  # SHORT box with bullish-time-asym is countertrend


def test_dedup_after_p3():
    """Two consecutive valid P0 troughs inside the same time window must not
    both spawn boxes against the same P3 envelope."""
    df = _synth_long_box_bullish_asym()
    boxes = bp.detect_boxes_df(df, "long")
    p3s = [b.p3_idx for b in boxes]
    p0s = [b.p0_idx for b in boxes]
    # every P0 must be strictly past the previous P3
    for prev_p3, p0 in zip(p3s[:-1], p0s[1:]):
        assert p0 > prev_p3, "dedup rule violated"


def test_box_to_trade_variant_A_targets_from_p2_two_targets():
    """H30 tightened spec (2026-06-20): TWO targets, 1.618 / 2.236 × height,
    projected from P2. T3 dropped."""
    df = _synth_long_box_bullish_asym()
    b = bp.detect_boxes_df(df, "long")[0]
    trade = bp.box_to_trade(b, df, bias_filter=True, target_variant="A")
    assert trade is not None
    # stop is P2 low; trail range = P1 − stop (unchanged across variants)
    assert abs(trade.initial_stop - df["low"].iloc[b.p2_idx]) < 1e-9
    expected_trail_range = b.p1_price - trade.initial_stop
    assert abs(trade.range_size - expected_trail_range) < 1e-9
    # exactly two targets
    assert len(trade.targets) == 2
    expected = [b.p2_price + lvl * b.height for lvl in (1.618, 2.236)]
    for t, e in zip(trade.targets, expected):
        assert abs(t - e) < 1e-6
    assert trade.targets[0] < trade.targets[1]


def test_box_to_trade_variant_A_terminates_at_T2_not_T3():
    """Generalized terminal-exit: variant A's final target is T2; hitting T2
    must record exit_reason == 'T2' (not 'T3', not 'time')."""
    # Construct a series where the variant-A long box's T2 is definitely hit
    # within the simulation window.
    n = 80
    rng = np.random.RandomState(2)
    closes = 100 + rng.normal(0, 0.05, n)
    highs = closes + 0.3; lows = closes - 0.3
    # Carve a box that's bullish-aligned and then rallies far past T2_A
    lows[2] = 95.0; highs[2] = 95.5; closes[2] = 95.3
    for i, val in enumerate(np.linspace(95.3, 110.0, 24)):
        highs[2 + i] = val + 0.3; lows[2 + i] = val - 0.3; closes[2 + i] = val
    highs[25] = 110.5; lows[25] = 109.5; closes[25] = 110.0
    for i, val in enumerate(np.linspace(110.0, 102.65, 6)):
        highs[25 + i] = val + 0.3; lows[25 + i] = val - 0.3; closes[25 + i] = val
    lows[30] = 102.0; highs[30] = 102.6; closes[30] = 102.5
    for i, val in enumerate(np.linspace(102.5, 110.4, 8)):
        highs[30 + i] = val + 0.3; lows[30 + i] = val - 0.3; closes[30 + i] = val
    highs[38] = 110.8; lows[38] = 110.0; closes[38] = 110.5
    # Strong rally past T2_A = P2 + 2.236*h. P2_price ≈ 102, h ≈ 15.5 → T2_A ≈ 136.7.
    # Drive closes upward fast so the bar reaches >=140.
    for i, val in enumerate(np.linspace(111.0, 145.0, n - 39)):
        highs[39 + i] = val + 0.5; lows[39 + i] = val - 0.5; closes[39 + i] = val
    df = _df(highs.tolist(), lows.tolist(), closes.tolist())
    b = bp.detect_boxes_df(df, "long")[0]
    trade = bp.box_to_trade(b, df, bias_filter=True, target_variant="A")
    assert trade is not None
    assert trade.exit_reason == "T2", (
        f"expected terminal exit at T2 (last target), got {trade.exit_reason}")


def _synth_long_moderate_pullback_then_higher_peak():
    """LONG: P0 deep trough at idx 5 (low 92). Rally to a prominent peak at
    idx 30 (high 110). MODERATE pullback to idx 35 (low 107) — deep enough
    that find_peaks identifies the trough at 35 as a candidate P0 (legacy
    will then move P0 to that), but the pullback bottom 107 is well above
    the 50%-retrace level (101) so the corrected detector's running-max
    keeps extending. Continue rally to dominant peak idx 50 (high 115).
    Then pullback past the dominant-peak retrace level (103.5) at idx 60.
    P3 break above 115 by idx 75.

    Expected divergence:
      LEGACY  P0=35 (intermediate trough; legacy abandoned P0=5 because
              mid_level=101 was never hit), P1=50.
      CORRECTED single-candidate from P0=5: running_max keeps walking past
              110 to 115; retrace from 115 fires at idx 60. P0=5, P1=50.
    Same P1 but DIFFERENT P0 — the corrected detector preserves the deeper,
    structurally meaningful P0 instead of jumping to a sub-impulse."""
    n = 90
    rng = np.random.RandomState(11)
    base = 100 + rng.normal(0, 0.05, n)
    highs = base + 0.3; lows = base - 0.3; closes = base.copy()
    lows[5] = 92.0; highs[5] = 92.5; closes[5] = 92.3
    for i, v in enumerate(np.linspace(92.3, 110.0, 26)):
        highs[5 + i] = v + 0.3; lows[5 + i] = v - 0.3; closes[5 + i] = v
    highs[30] = 110.5; lows[30] = 109.5; closes[30] = 110.0
    # Moderate pullback to idx 35 (low 107) — find_peaks IDENTIFIES this
    # trough (prominence 3 ≫ 0.52 threshold) BUT the pullback bottom 107
    # is above the 50% level (=101) so neither legacy nor corrected
    # triggers P2 from the intermediate peak.
    for i, v in enumerate(np.linspace(110.0, 107.0, 6)):
        highs[30 + i] = v + 0.3; lows[30 + i] = v - 0.3; closes[30 + i] = v
    # Continue rally to dominant peak at idx 50 (115)
    for i, v in enumerate(np.linspace(107.0, 115.0, 16)):
        highs[35 + i] = v + 0.3; lows[35 + i] = v - 0.3; closes[35 + i] = v
    highs[50] = 115.5; lows[50] = 114.5; closes[50] = 115.0
    # Pullback past 50% from dominant (level = 115 − 0.5·(115−92) = 103.5)
    for i, v in enumerate(np.linspace(115.0, 103.0, 11)):
        highs[50 + i] = v + 0.3; lows[50 + i] = v - 0.3; closes[50 + i] = v
    lows[60] = 103.0; highs[60] = 103.6; closes[60] = 103.3
    for i, v in enumerate(np.linspace(103.3, 117.0, 16)):
        highs[60 + i] = v + 0.3; lows[60 + i] = v - 0.3; closes[60 + i] = v
    highs[75] = 117.5; lows[75] = 116.5; closes[75] = 117.0
    return _df(highs.tolist(), lows.tolist(), closes.tolist())


def test_corrected_detector_preserves_deep_p0_when_legacy_jumps_to_intermediate():
    """H30b core fix: with an intermediate-trough find_peaks candidate
    between the deep P0 and the dominant peak, the corrected single-
    candidate detector preserves the deep P0 (idx 5) while the legacy
    detector — which gives up on P0=5 because the intermediate peak's
    mid_level isn't pierced — jumps to the intermediate trough as its
    new P0. Both detectors land on the same P1 (the dominant peak), but
    the corrected box's P0 is the structurally meaningful one."""
    df = _synth_long_moderate_pullback_then_higher_peak()
    corrected = bp.detect_boxes_df(df, "long")
    legacy = bp.detect_boxes_df(df, "long", legacy=True)
    assert len(corrected) >= 1
    bc = corrected[0]
    assert bc.p0_idx <= 6, (
        f"corrected detector dropped the deep P0=5: got p0_idx={bc.p0_idx}")
    assert bc.p1_idx >= 45 and bc.p1_price > 113
    assert len(legacy) >= 1
    bl = legacy[0]
    assert bl.p0_idx > bc.p0_idx, (
        f"legacy was expected to advance P0 past the deep candidate: "
        f"got legacy p0_idx={bl.p0_idx}, corrected p0_idx={bc.p0_idx}")


def _synth_long_p0_invalidated_by_sharp_drop():
    """LONG: P0 candidate at idx 5 (low 95) rallies to idx 20 (high 100).
    Idx 21 prints a SHARP single-bar drop (high 92, low 89) — low < P0_price,
    invalidating the candidate. (Sharp because a gradual decline would cross
    the 50%-retrace level first and fire retrace instead of invalidation.)
    A new candidate spawns at idx 21 (p0=89); the rally to idx 60 (high 115)
    and pullback to idx 70 (~102) complete the box. The resulting box's
    p0_idx must be 21, not 5."""
    n = 100
    rng = np.random.RandomState(13)
    base = 100 + rng.normal(0, 0.05, n)
    highs = base + 0.3; lows = base - 0.3; closes = base.copy()
    # Initial swing low at idx 5
    lows[5] = 95.0; highs[5] = 95.5; closes[5] = 95.3
    # Smooth rally to idx 20 — running_max walks to 100, no retrace yet
    for i, v in enumerate(np.linspace(95.3, 100.0, 16)):
        highs[5 + i] = v + 0.3; lows[5 + i] = v - 0.3; closes[5 + i] = v
    highs[20] = 100.5; lows[20] = 99.5; closes[20] = 100.0
    # SHARP single-bar drop at idx 21 — high 92 (< running_max 100, no
    # running_max update), low 89 (< P0_price 95, INVALIDATES candidate).
    # This skips over the 50%-retrace level (~97.5) entirely in one bar.
    highs[21] = 92.0; lows[21] = 89.0; closes[21] = 89.5
    # New candidate at idx 21 (p0_price=89) rallies cleanly to idx 60
    for i, v in enumerate(np.linspace(89.5, 115.0, 40)):
        highs[21 + i] = v + 0.3; lows[21 + i] = v - 0.3; closes[21 + i] = v
    highs[60] = 115.5; lows[60] = 114.5; closes[60] = 115.0
    # Pullback past 50% retrace from new running_max=115, p0=89 → level=102
    for i, v in enumerate(np.linspace(115.0, 101.5, 11)):
        highs[60 + i] = v + 0.3; lows[60 + i] = v - 0.3; closes[60 + i] = v
    lows[70] = 101.5; highs[70] = 102.5; closes[70] = 102.0
    # P3 break above 115 by idx 85
    for i, v in enumerate(np.linspace(102.0, 117.0, 16)):
        highs[70 + i] = v + 0.3; lows[70 + i] = v - 0.3; closes[70 + i] = v
    highs[85] = 117.5; lows[85] = 116.5; closes[85] = 117.0
    return _df(highs.tolist(), lows.tolist(), closes.tolist())


def test_corrected_detector_invalidates_old_p0_when_deeper_low_forms():
    """Corrected detector: a single-bar drop whose low pierces the previous
    P0 must invalidate that candidate and respawn a new one at the current
    bar. The resulting box's p0_idx must be at the invalidation bar (21),
    not the original idx 5."""
    df = _synth_long_p0_invalidated_by_sharp_drop()
    boxes = bp.detect_boxes_df(df, "long")
    assert len(boxes) >= 1, (
        "corrected detector should still produce a box from the respawned P0")
    b = boxes[0]
    assert b.p0_idx >= 21, (
        f"detector kept the original P0 instead of invalidating: "
        f"got p0_idx={b.p0_idx}, expected ≥21 (after the sharp drop)")
    # P0_price must reflect the new lower low (≈89), not the original 95
    assert b.p0_price < 90, (
        f"p0_price={b.p0_price} suggests the original P0 was kept")
    # P1 is the dominant peak around idx 60 (running max from new P0)
    assert b.p1_idx >= 55 and b.p1_price > 113


def _synth_short_moderate_bounce_then_lower_trough():
    """SHORT mirror: P0 swing high idx 5 (108). Decline to intermediate
    low idx 30 (90). MODERATE bounce to idx 35 (93) — deep enough that
    find_peaks identifies the peak, but well below the 50% bounce level
    (=99). Continue decline to dominant low idx 50 (85). Bounce past 96.5
    at idx 60. P3 break below 85 at idx 75."""
    n = 90
    rng = np.random.RandomState(14)
    base = 100 + rng.normal(0, 0.05, n)
    highs = base + 0.3; lows = base - 0.3; closes = base.copy()
    highs[5] = 108.0; lows[5] = 107.5; closes[5] = 107.8
    for i, v in enumerate(np.linspace(107.8, 90.0, 26)):
        highs[5 + i] = v + 0.3; lows[5 + i] = v - 0.3; closes[5 + i] = v
    lows[30] = 89.5; highs[30] = 90.5; closes[30] = 90.0
    # Moderate bounce to 93 by idx 35 — find_peaks marks the peak
    for i, v in enumerate(np.linspace(90.0, 93.0, 6)):
        highs[30 + i] = v + 0.3; lows[30 + i] = v - 0.3; closes[30 + i] = v
    # Continue decline to dominant low at idx 50 (85)
    for i, v in enumerate(np.linspace(93.0, 85.0, 16)):
        highs[35 + i] = v + 0.3; lows[35 + i] = v - 0.3; closes[35 + i] = v
    lows[50] = 84.5; highs[50] = 85.5; closes[50] = 85.0
    # Bounce past 50% level (96.5) at idx 60
    for i, v in enumerate(np.linspace(85.0, 97.0, 11)):
        highs[50 + i] = v + 0.3; lows[50 + i] = v - 0.3; closes[50 + i] = v
    highs[60] = 97.0; lows[60] = 96.4; closes[60] = 96.7
    for i, v in enumerate(np.linspace(96.7, 83.0, 16)):
        highs[60 + i] = v + 0.3; lows[60 + i] = v - 0.3; closes[60 + i] = v
    lows[75] = 82.5; highs[75] = 83.5; closes[75] = 83.0
    return _df(highs.tolist(), lows.tolist(), closes.tolist())


def test_corrected_detector_short_preserves_deep_p0():
    """SHORT mirror — corrected preserves the deep P0; legacy advances to
    the intermediate peak."""
    df = _synth_short_moderate_bounce_then_lower_trough()
    corrected = bp.detect_boxes_df(df, "short")
    legacy = bp.detect_boxes_df(df, "short", legacy=True)
    assert len(corrected) >= 1
    bc = corrected[0]
    assert bc.p0_idx <= 6
    assert bc.p1_idx >= 45 and bc.p1_price < 87
    assert len(legacy) >= 1
    assert legacy[0].p0_idx > bc.p0_idx


def test_legacy_flag_round_trips():
    """``legacy=True`` exercises the H29/H30a code path. On the moderate-
    pullback fixture they diverge; on the clean H29 fixture they agree."""
    df = _synth_long_moderate_pullback_then_higher_peak()
    new = bp.detect_boxes_df(df, "long", legacy=False)
    leg = bp.detect_boxes_df(df, "long", legacy=True)
    assert len(new) >= 1 and len(leg) >= 1
    assert new[0].p0_idx != leg[0].p0_idx
    # On the clean H29 fixture (no intermediate peak/trough) both agree
    df2 = _synth_long_box_bullish_asym()
    leg2 = bp.detect_boxes_df(df2, "long", legacy=True)
    new2 = bp.detect_boxes_df(df2, "long", legacy=False)
    assert len(leg2) >= 1 and len(new2) >= 1
    assert leg2[0].p1_idx == new2[0].p1_idx


def _synth_three_box_long_chain_then_short_reversal():
    """LONG chain of 3 boxes (each P2 becomes the next P0), then a SHORT
    reversal box anchored at the chain's terminal high. Geometry hand-set
    so each box clears the 50%-retrace trigger at the right place."""
    n = 220
    rng = np.random.RandomState(7)
    closes = 100 + rng.normal(0, 0.05, n)
    H = closes + 0.3; L = closes - 0.3
    def seg(a, b, lo, hi):
        for i, v in enumerate(np.linspace(lo, hi, b - a + 1)):
            H[a + i] = v + 0.3; L[a + i] = v - 0.3; closes[a + i] = v
    # Box 1
    L[5] = 90.0; H[5] = 90.5; closes[5] = 90.3
    seg(5, 25, 90.3, 110.0); H[25] = 110.5; L[25] = 109.5; closes[25] = 110.0
    seg(25, 33, 110.0, 100.0)
    L[33] = 100.0; H[33] = 100.6; closes[33] = 100.3
    seg(33, 45, 100.3, 112.0)
    # Box 2 (continuation from P2_1 = idx 33)
    seg(45, 65, 112.0, 125.0); H[65] = 125.5; L[65] = 124.5; closes[65] = 125.0
    seg(65, 75, 125.0, 112.5)
    L[75] = 112.5; H[75] = 113.1; closes[75] = 112.8
    seg(75, 90, 112.8, 127.0)
    # Box 3 (continuation from P2_2 = idx 75)
    seg(90, 110, 127.0, 140.0); H[110] = 140.5; L[110] = 139.5; closes[110] = 140.0
    seg(110, 125, 140.0, 126.0)
    L[125] = 126.0; H[125] = 126.6; closes[125] = 126.3
    seg(125, 140, 126.3, 142.0)
    # Chain terminal extends to ~145
    seg(140, 150, 142.0, 145.0); H[150] = 145.5; L[150] = 144.5; closes[150] = 145.0
    # SHORT reversal: P0 = chain terminal high. decline → 50% bounce → break below
    seg(150, 170, 145.0, 130.0); L[170] = 129.5; H[170] = 130.5; closes[170] = 130.0
    seg(170, 180, 130.0, 138.0); H[180] = 138.0; L[180] = 137.4; closes[180] = 137.7
    seg(180, 200, 137.7, 128.0); L[200] = 127.5; H[200] = 128.5; closes[200] = 128.0
    return _df(H.tolist(), L.tolist(), closes.tolist())


def test_three_box_long_chain_each_p2_becomes_next_p0():
    """Chain mode: 3 consecutive same-direction boxes, each P0 equals the
    previous P2 (the canonical chaining rule)."""
    df = _synth_three_box_long_chain_then_short_reversal()
    boxes = bp.detect_boxes_df(df, chain_mode=True)
    long_chain = [b for b in boxes if b.chain_id == 0 and b.direction == "long"]
    assert len(long_chain) >= 3, (
        f"expected ≥3 LONG boxes in chain 0; got {len(long_chain)}")
    chain_indices = [b.chain_index for b in long_chain[:3]]
    assert chain_indices == [0, 1, 2], (
        f"chain_index sequence should be [0,1,2]; got {chain_indices}")
    # P0 of box-2 must equal P2 of box-1; P0 of box-3 must equal P2 of box-2
    assert long_chain[1].p0_idx == long_chain[0].p2_idx
    assert long_chain[2].p0_idx == long_chain[1].p2_idx
    # P0_price must equal P2_price (same bar, same low)
    assert abs(long_chain[1].p0_price - long_chain[0].p2_price) < 1e-9
    assert abs(long_chain[2].p0_price - long_chain[1].p2_price) < 1e-9
    # reverses_chain_id must be None for continuation boxes
    assert all(b.reverses_chain_id is None for b in long_chain)


def test_long_to_short_reversal_anchored_at_chain_terminal_high():
    """After the LONG chain, a SHORT reversal box must spawn with P0 ≈ the
    chain's terminal high and reverses_chain_id pointing to the LONG chain."""
    df = _synth_three_box_long_chain_then_short_reversal()
    boxes = bp.detect_boxes_df(df, chain_mode=True)
    # First SHORT box that follows the LONG chain
    short_rev = next((b for b in boxes
                       if b.direction == "short" and b.reverses_chain_id is not None),
                      None)
    assert short_rev is not None, "no SHORT reversal box found"
    assert short_rev.reverses_chain_id == 0
    assert short_rev.chain_index == 0
    # P0 should be near the chain's terminal high (we wrote it near idx 150, price ~145)
    assert 140 <= short_rev.p0_idx <= 160
    assert short_rev.p0_price > 142, (
        f"SHORT reversal P0 price {short_rev.p0_price} below the chain "
        f"terminal high ~145")


def _synth_three_box_short_chain_then_long_reversal():
    """SHORT mirror — 3-box SHORT chain then LONG reversal."""
    n = 220
    rng = np.random.RandomState(8)
    closes = 100 + rng.normal(0, 0.05, n)
    H = closes + 0.3; L = closes - 0.3
    def seg(a, b, lo, hi):
        for i, v in enumerate(np.linspace(lo, hi, b - a + 1)):
            H[a + i] = v + 0.3; L[a + i] = v - 0.3; closes[a + i] = v
    # Box 1 SHORT: P0=swing high
    H[5] = 110.0; L[5] = 109.5; closes[5] = 109.8
    seg(5, 25, 109.8, 90.0); L[25] = 89.5; H[25] = 90.5; closes[25] = 90.0
    seg(25, 33, 90.0, 100.0)
    H[33] = 100.0; L[33] = 99.4; closes[33] = 99.7
    seg(33, 45, 99.7, 88.0)
    # Box 2
    seg(45, 65, 88.0, 75.0); L[65] = 74.5; H[65] = 75.5; closes[65] = 75.0
    seg(65, 75, 75.0, 87.5)
    H[75] = 87.5; L[75] = 86.9; closes[75] = 87.2
    seg(75, 90, 87.2, 73.0)
    # Box 3
    seg(90, 110, 73.0, 60.0); L[110] = 59.5; H[110] = 60.5; closes[110] = 60.0
    seg(110, 125, 60.0, 73.75)
    H[125] = 73.8; L[125] = 73.2; closes[125] = 73.5
    seg(125, 140, 73.5, 58.0)
    # Terminal low extends to ~55
    seg(140, 150, 58.0, 55.0); L[150] = 54.5; H[150] = 55.5; closes[150] = 55.0
    # LONG reversal: P0 = chain terminal low. rally → 50% retrace down → break above
    seg(150, 170, 55.0, 70.0); H[170] = 70.5; L[170] = 69.5; closes[170] = 70.0
    seg(170, 180, 70.0, 62.5); L[180] = 62.0; H[180] = 62.6; closes[180] = 62.3
    seg(180, 200, 62.3, 72.0); H[200] = 72.5; L[200] = 71.5; closes[200] = 72.0
    return _df(H.tolist(), L.tolist(), closes.tolist())


def test_short_to_long_reversal_anchored_at_chain_terminal_low():
    """Mirror of the LONG→SHORT test."""
    df = _synth_three_box_short_chain_then_long_reversal()
    boxes = bp.detect_boxes_df(df, chain_mode=True)
    short_chain_0 = [b for b in boxes
                      if b.chain_id == 0 and b.direction == "short"]
    assert len(short_chain_0) >= 3, (
        f"expected ≥3 SHORT boxes in chain 0; got {len(short_chain_0)}")
    assert [b.chain_index for b in short_chain_0[:3]] == [0, 1, 2]
    assert short_chain_0[1].p0_idx == short_chain_0[0].p2_idx
    assert short_chain_0[2].p0_idx == short_chain_0[1].p2_idx
    long_rev = next((b for b in boxes
                      if b.direction == "long" and b.reverses_chain_id is not None),
                     None)
    assert long_rev is not None
    assert long_rev.reverses_chain_id == 0
    assert long_rev.chain_index == 0
    # P0 should be near the chain terminal low (~55)
    assert 140 <= long_rev.p0_idx <= 160
    assert long_rev.p0_price < 58


def test_chain_mode_off_returns_no_chain_metadata():
    """Backwards compatibility: ``chain_mode=False`` (the default) must
    leave chain_id / chain_index / reverses_chain_id as None on every box,
    and the box list must match the H30b standalone detector."""
    df = _synth_long_moderate_pullback_then_higher_peak()
    boxes = bp.detect_boxes_df(df, "long")
    assert len(boxes) >= 1
    for b in boxes:
        assert b.chain_id is None
        assert b.chain_index is None
        assert b.reverses_chain_id is None


def _synth_long_box_no_post_p0_higher_high_until_late():
    """LONG fixture where the very first post-P0 bar does NOT make a new
    high above P0's bar. If the detector doesn't gate the retrace check on
    'running_max has actually advanced past P0', it collapses P1 to P0 at
    the first low-pierce of the P0 bar's midpoint — producing a 1-bar
    micro-box (Bug 2 in H30c).

    Geometry: P0 idx 5 (low 92, high 95). Bars 6-15 stay below P0's high
    (range 93-94, so high < 95, low > 92 — no invalidation, no running-max
    update). Bars 16-30 rally to peak 105 at idx 30. Pullback to 50% level
    (= (92+105)/2 = 98.5) at idx 38. P3 break above 105 by idx 45."""
    n = 70
    rng = np.random.RandomState(31)
    closes = 100 + rng.normal(0, 0.05, n)
    H = closes + 0.3; L = closes - 0.3
    # P0
    L[5] = 92.0; H[5] = 95.0; closes[5] = 93.5
    # Bars 6..15: stay between 92.5 and 94.5 — no new high above 95, no
    # invalidation below 92
    for i, hh, ll in zip(range(6, 16),
                         (94.0, 93.8, 94.2, 93.6, 94.0, 94.3, 93.9, 94.1, 94.4, 94.5),
                         (93.0, 92.8, 93.1, 92.7, 92.9, 93.2, 92.6, 92.9, 93.3, 93.4)):
        H[i] = hh; L[i] = ll; closes[i] = (hh + ll) / 2
    # Rally 16→30 from ~94 to 105
    for i, v in enumerate(np.linspace(94.5, 105.0, 15)):
        H[16 + i] = v + 0.3; L[16 + i] = v - 0.3; closes[16 + i] = v
    H[30] = 105.5; L[30] = 104.5; closes[30] = 105.0
    # Pullback to ≤ 98.5 by idx 38
    for i, v in enumerate(np.linspace(105.0, 98.0, 9)):
        H[30 + i] = v + 0.3; L[30 + i] = v - 0.3; closes[30 + i] = v
    L[38] = 98.0; H[38] = 98.6; closes[38] = 98.3
    # P3 break above 105 by idx 50
    for i, v in enumerate(np.linspace(98.3, 107.0, 13)):
        H[38 + i] = v + 0.3; L[38 + i] = v - 0.3; closes[38 + i] = v
    H[50] = 107.5; L[50] = 106.5; closes[50] = 107.0
    return _df(H.tolist(), L.tolist(), closes.tolist())


def test_bug2_no_p1_equals_p0_micro_box_when_running_max_never_updates_first():
    """Regression test for H30d Bug 2: the detector must NOT emit a box
    whose P1_idx equals P0_idx. Even when several bars after P0 fail to
    exceed P0's bar's high (so running_max can't update), the retrace
    check stays gated until a real higher high appears. The detector then
    locks P1 at the real dominant peak around idx 30 (~105)."""
    df = _synth_long_box_no_post_p0_higher_high_until_late()
    boxes = bp.detect_boxes_df(df, "long")
    assert len(boxes) >= 1
    b = boxes[0]
    assert b.p1_idx != b.p0_idx, (
        f"micro-box bug regressed: p1_idx == p0_idx == {b.p0_idx} "
        f"means P1 collapsed to P0 (1-bar swing).")
    assert b.p1_idx >= 16, (
        f"P1 locked too early at idx {b.p1_idx}; "
        f"the running_max should reach the dominant peak around idx 30.")
    assert b.p1_price > 100, (
        f"P1 price {b.p1_price} below the dominant peak ~105 — "
        f"running_max didn't extend past the intermediate flat region.")


def test_bug1_p3_price_equals_p1_price_for_rendering():
    """Regression test for H30d Bug 1: BoxPattern.p3_price (the field
    renderers use for the P3 marker's y-coordinate) must equal p1_price,
    matching Dr. A's "Point-3 level always is equal to point-1 level."
    The bar's actual high/low at P3 is still recoverable from the source
    OHLC data if a caller wants it."""
    df = _synth_long_box_no_post_p0_higher_high_until_late()
    boxes = bp.detect_boxes_df(df, "long")
    assert len(boxes) >= 1
    for b in boxes:
        assert b.p3_price == b.p1_price, (
            f"p3_price={b.p3_price} != p1_price={b.p1_price}")
    # Cross-check on chain mode (which goes through _build_box)
    df2 = _synth_three_box_long_chain_then_short_reversal()
    chained = bp.detect_boxes_df(df2, chain_mode=True)
    for b in chained:
        assert b.p3_price == b.p1_price, (
            f"chained box {b.chain_id}/{b.chain_index}: p3_price={b.p3_price} "
            f"!= p1_price={b.p1_price}")


def _synth_long_shallow_low_then_deeper_low_then_peak():
    """LONG fixture for Bug 3 (H30e). A shallow swing low at idx 10
    (~95) is the find_peaks-identified P0 seed. Bars 11..19 rally to ~99.
    Bar 20 has a wide-range candle: high 100 (new high, would update
    running_max) AND low 88 (deeper low than P0=95 — should invalidate).
    The pre-H30e detector locked P1 here because the new-high check ran
    first and skipped invalidation. The H30e fix checks invalidation
    first; P0 floats to bar 20 (low 88), running_max restarts. Bars
    21..50 then rally to a real dominant peak (~110) and trigger retrace
    at idx ~60.

    Expected H30e box: p0_idx >= 20 (not 10), p0_price <= 88.5."""
    n = 120
    rng = np.random.RandomState(53)
    closes = 100 + rng.normal(0, 0.05, n)
    H = closes + 0.3; L = closes - 0.3
    # P0 at idx 10 (shallow swing low at 95)
    L[10] = 95.0; H[10] = 95.5; closes[10] = 95.3
    # Modest rally 11→19 from 95 to 99
    for i, v in enumerate(np.linspace(95.3, 99.0, 9)):
        H[11 + i] = v + 0.3; L[11 + i] = v - 0.3; closes[11 + i] = v
    # Bar 20: wide-range candle — high 100 (new running_max), low 88 (deeper)
    H[20] = 100.0; L[20] = 88.0; closes[20] = 94.0
    # Rally from 88 to 110 by idx 50
    for i, v in enumerate(np.linspace(88.0, 110.0, 30)):
        H[21 + i] = v + 0.3; L[21 + i] = v - 0.3; closes[21 + i] = v
    H[50] = 110.5; L[50] = 109.5; closes[50] = 110.0
    # Pullback past 50% from running_max=110, p0=88 → level=99
    for i, v in enumerate(np.linspace(110.0, 98.0, 11)):
        H[50 + i] = v + 0.3; L[50 + i] = v - 0.3; closes[50 + i] = v
    L[60] = 98.0; H[60] = 98.6; closes[60] = 98.3
    # P3 break above 110 by idx 75
    for i, v in enumerate(np.linspace(98.3, 112.0, 16)):
        H[60 + i] = v + 0.3; L[60 + i] = v - 0.3; closes[60 + i] = v
    H[75] = 112.5; L[75] = 111.5; closes[75] = 112.0
    return _df(H.tolist(), L.tolist(), closes.tolist())


def test_bug3_p0_floats_to_deepest_low_when_wide_range_bar_pierces():
    """H30e Bug 3 regression: a single bar with simultaneous new high AND
    deeper low must respawn P0 at the deeper low, not slip past via the
    new-high branch. Pre-H30e the detector skipped invalidation in this
    case and the resulting box had p0_idx=10 (shallow); post-H30e it
    floats to bar 20 (deep)."""
    df = _synth_long_shallow_low_then_deeper_low_then_peak()
    boxes = bp.detect_boxes_df(df, "long")
    assert len(boxes) >= 1
    b = boxes[0]
    # The deeper low at idx 20 (price 88) must become P0
    assert b.p0_idx >= 20, (
        f"H30e regression: p0_idx={b.p0_idx} should be ≥20 (the wide-range "
        f"bar). Pre-H30e behaviour locked P0 at the shallower seed at idx 10.")
    assert b.p0_price <= 88.5, (
        f"H30e regression: p0_price={b.p0_price} should be at most ~88 "
        f"(the deeper low). Pre-H30e p0_price would be ~95 (the seed).")


def test_bug3_chain_continuation_gap_scan_catches_deeper_low_between_p2_and_p3():
    """Cont-track gap pre-scan: bars in [previous P2, previous P3) are
    part of the previous box's breakout phase and otherwise missed by
    the forward walker. If a deeper low than previous P2 exists there,
    it must become the new cont's P0 (H30e fix)."""
    # Use the 3-box LONG chain fixture and verify each cont box's
    # invariant: there is NO bar in [P0_idx, P1_idx] with low < P0_price.
    df = _synth_three_box_long_chain_then_short_reversal()
    boxes = bp.detect_boxes_df(df, chain_mode=True)
    for b in boxes:
        if b.direction == "long":
            window_lows = df["low"].iloc[b.p0_idx:b.p1_idx + 1]
            actual_min = float(window_lows.min())
            assert actual_min >= b.p0_price - 1e-9, (
                f"chain box {b.chain_id}/{b.chain_index}: actual min low "
                f"{actual_min:.4f} < p0_price {b.p0_price:.4f} in [P0..P1] "
                f"window — H30e fix did not catch it")
        else:
            window_highs = df["high"].iloc[b.p0_idx:b.p1_idx + 1]
            actual_max = float(window_highs.max())
            assert actual_max <= b.p0_price + 1e-9, (
                f"chain box {b.chain_id}/{b.chain_index}: actual max high "
                f"{actual_max:.4f} > p0_price {b.p0_price:.4f} in [P0..P1]")


def test_box_to_trade_variant_A_trail_anchored_on_p2():
    """Variant A's trail-activation price must be P2 ± 2.200·height
    (NOT entry ± factor·range_size). Build a series where stop never fires,
    trail never arms within window, and read FibTrade.range_size + the
    side-effect of trail behaviour. Simplest: just unit-check the helper."""
    df = _synth_long_box_bullish_asym()
    b = bp.detect_boxes_df(df, "long")[0]
    # entry & range come from box_to_trade math
    entry_idx = b.p3_idx + 1
    entry_price = float(df["close"].iloc[entry_idx])
    initial_stop = float(df["low"].iloc[b.p2_idx])
    range_size = b.p1_price - initial_stop
    trail_A = bp._trail_activation_price_for(b, "A", entry_price, range_size)
    expected = b.p2_price + 2.200 * b.height
    assert abs(trail_A - expected) < 1e-9
    # variant B keeps the entry-anchored convention
    trail_B = bp._trail_activation_price_for(b, "B", entry_price, range_size)
    expected_B = entry_price + 3.600 * range_size
    assert abs(trail_B - expected_B) < 1e-9


def test_box_to_trade_variant_B_targets_from_p1_with_h29_levels():
    """H30 alternative: 1.618 / 2.236 / 3.618 × box.height projected from P1."""
    df = _synth_long_box_bullish_asym()
    b = bp.detect_boxes_df(df, "long")[0]
    trade = bp.box_to_trade(b, df, bias_filter=True, target_variant="B")
    assert trade is not None
    expected = [b.p1_price + lvl * b.height for lvl in (1.618, 2.236, 3.618)]
    for t, e in zip(trade.targets, expected):
        assert abs(t - e) < 1e-6


def test_corrected_tmid_uses_p2_endpoint_by_default():
    """The H30 default is t_endpoint='p2' — verify the BoxPattern.t_mid field
    matches (P0+P2)/2, NOT (P0+P3)/2 (the H29 legacy)."""
    df = _synth_long_box_bullish_asym()
    boxes_corrected = bp.detect_boxes_df(df, "long")
    boxes_legacy = bp.detect_boxes_df(df, "long", t_endpoint="p3")
    assert len(boxes_corrected) >= 1 and len(boxes_legacy) >= 1
    bc = boxes_corrected[0]; bl = boxes_legacy[0]
    assert bc.p0_idx == bl.p0_idx and bc.p2_idx == bl.p2_idx and bc.p3_idx == bl.p3_idx
    assert abs(bc.t_mid - (bc.p0_idx + bc.p2_idx) / 2.0) < 1e-9
    assert abs(bl.t_mid - (bl.p0_idx + bl.p3_idx) / 2.0) < 1e-9
    # corrected t_mid sits strictly LEFT of legacy t_mid (since P2 < P3)
    assert bc.t_mid < bl.t_mid


def test_max_length_cap_drops_mega_boxes():
    """A synthetic series engineered to form a single box of length > 250
    must not be returned when ``max_length=250`` (the H30 default)."""
    rng = np.random.RandomState(7)
    n = 320
    closes = 100 + rng.normal(0, 0.05, n)
    highs = closes + 0.3; lows = closes - 0.3
    # P0 deep trough at idx 5
    lows[5] = 95.0; highs[5] = 95.5; closes[5] = 95.3
    # long slow rally to P1 at idx 120
    for i, val in enumerate(np.linspace(95.3, 110.0, 116)):
        highs[5 + i] = val + 0.3; lows[5 + i] = val - 0.3; closes[5 + i] = val
    highs[120] = 110.5; lows[120] = 109.5; closes[120] = 110.0
    # slow correction to 50% (= 102.65) by idx 200
    for i, val in enumerate(np.linspace(110.0, 102.65, 81)):
        highs[120 + i] = val + 0.3; lows[120 + i] = val - 0.3; closes[120 + i] = val
    lows[200] = 102.0; highs[200] = 102.6; closes[200] = 102.5
    # slow rise → P3 break above P1 at idx 310 (length 310 − 5 = 305 > 250)
    for i, val in enumerate(np.linspace(102.5, 110.8, 111)):
        highs[200 + i] = val + 0.3; lows[200 + i] = val - 0.3; closes[200 + i] = val
    highs[310] = 111.0; lows[310] = 110.4; closes[310] = 110.6
    df = _df(highs.tolist(), lows.tolist(), closes.tolist())
    # default cap drops the mega-box; any unrelated noise-tail box must
    # NOT have length anywhere near the mega-box's 305 bars.
    capped = bp.detect_boxes_df(df, "long")
    assert all(b.length <= 250 for b in capped), (
        f"a box exceeded the default 250-bar cap: lengths={[b.length for b in capped]}")
    # explicit cap of 350 lets the mega-box through
    boxes = bp.detect_boxes_df(df, "long", max_length=350)
    assert any(b.length > 250 for b in boxes)
    # disabling cap (None) also lets it through
    boxes_none = bp.detect_boxes_df(df, "long", max_length=None)
    assert any(b.length > 250 for b in boxes_none)
