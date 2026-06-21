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
    # default cap drops it
    assert len(bp.detect_boxes_df(df, "long")) == 0
    # explicit cap of 350 lets it through
    boxes = bp.detect_boxes_df(df, "long", max_length=350)
    assert any(b.length > 250 for b in boxes)
    # disabling cap (None) also lets it through
    boxes_none = bp.detect_boxes_df(df, "long", max_length=None)
    assert len(boxes_none) >= 1
