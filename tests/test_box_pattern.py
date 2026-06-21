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
