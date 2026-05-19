"""V-SHORT vs M-LONG symmetry tests.

The part most likely to carry a subtle long-vs-short asymmetry is the
3-bar trailing stop and its inside-bar exclusion. This test pins the
invariant: reflecting price through zero (high ↔ −low, low ↔ −high) must
turn the long-side trailing stop into the negated short-side trailing
stop, bar-for-bar, INCLUDING the inside-bar skip and the no-fill
sentinels (long → −inf, short → +inf).

If this test ever fails, the V-SHORT pipeline is not a faithful mirror of
M-LONG and cross-direction comparisons (H25) are invalid.
"""
import math

import numpy as np
import pandas as pd
import pytest

from rsi_pattern import strategies_vshort as vs


def _reflect(df: pd.DataFrame) -> pd.DataFrame:
    """Mirror prices through zero. A higher-high series becomes a
    lower-low series; inside bars stay inside bars."""
    return pd.DataFrame({
        "open": -df["open"],
        "high": -df["low"],
        "low": -df["high"],
        "close": -df["close"],
    }, index=df.index)


@pytest.fixture
def synthetic_ohlc() -> pd.DataFrame:
    """20 bars: a clean rising staircase with two embedded inside bars
    (bars 7 and 13) so the inside-bar exclusion is exercised on both
    sides, plus a flat tail so <3-pivot sentinel paths are hit on short
    windows."""
    highs = [10, 11, 12, 13, 14, 15, 16, 15.5, 17, 18,
             19, 20, 21, 20.4, 22, 23, 24, 25, 26, 27]
    lows = [9, 9.5, 10, 10.6, 11, 12, 13, 13.2, 14, 15,
            16, 17, 18, 18.1, 19, 20, 21, 22, 23, 24]
    idx = pd.date_range("2025-01-01", periods=len(highs), freq="D", tz="UTC")
    mid = [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame({"open": mid, "high": highs, "low": lows,
                         "close": mid}, index=idx)


def _eq(a: float, b: float) -> bool:
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) < 1e-9


@pytest.mark.parametrize("start,current", [
    (0, 2), (0, 6), (0, 7), (0, 13), (0, 19),
    (3, 9), (5, 14), (10, 19), (16, 19), (17, 19),
])
def test_trailing_stop_long_short_mirror(synthetic_ohlc, start, current):
    df = synthetic_ohlc
    dfr = _reflect(df)
    long_stop = vs.trailing_stop_long(df, start, current)
    short_stop_reflected = vs.trailing_stop_short(dfr, start, current)
    # long stop on the original == −(short stop on the reflected series)
    assert _eq(long_stop, -short_stop_reflected), (
        f"asymmetry at ({start},{current}): "
        f"long={long_stop} short_reflected={short_stop_reflected}")


def test_sentinels_are_mirrored(synthetic_ohlc):
    df = synthetic_ohlc
    dfr = _reflect(df)
    # Window too short for 3 pivots → long returns −inf, short returns +inf
    long_stop = vs.trailing_stop_long(df, 0, 1)
    short_stop = vs.trailing_stop_short(dfr, 0, 1)
    assert long_stop == -np.inf
    assert short_stop == np.inf
    assert _eq(long_stop, -short_stop)


def test_inside_bar_excluded_symmetrically(synthetic_ohlc):
    """Bar 7 (high 15.5 < prev 16, low 13.2 > prev 13) is an inside bar.
    It must be skipped by BOTH the long higher-high scan and, after
    reflection, the short lower-low scan — i.e. the mirror identity holds
    across a window that contains an inside bar."""
    df = synthetic_ohlc
    dfr = _reflect(df)
    # window 4..9 spans the inside bar at 7
    assert _eq(vs.trailing_stop_long(df, 4, 9),
               -vs.trailing_stop_short(dfr, 4, 9))
