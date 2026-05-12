"""Future Line of Demarcation (FLD) — simple price-shifted indicator.

Per Hickson/Hurst methodology, the FLD for a cycle of period N is the median
price shifted forward by ceil(N/2) bars. The trader compares current price
to the FLD level:
- price > FLD → bullish bias for that cycle
- price < FLD → bearish bias

Multi-cycle aggregation:
- agreement_count = (bullish_40 + bullish_80 + bullish_120) → 0 to 3
- bullish if ≥2 of 3 cycles agree
- bearish if ≤1 of 3 cycles agree
- neutral otherwise (mixed)

This is a SIMPLIFIED FLD. The full Hickson implementation uses Signal/Mid/
Sequence FLDs computed off Sentient Trader's cyclic analysis. For confluence
testing with RSI patterns, this approximation captures the directional bias.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd

# Canonical Hurst daily periods from hurst-agent (Signal / Mid / Sequence)
DEFAULT_CYCLES = (10, 20, 40)


def median_price(df: pd.DataFrame, high_col: str = "high", low_col: str = "low") -> pd.Series:
    return (df[high_col] + df[low_col]) / 2


def compute_fld(df: pd.DataFrame, cycle_bars: int, smooth: int = 1) -> pd.Series:
    """FLD per Hurst canonical: source = (high+low)/2, shift = period // 2 + 1.

    Matches the implementation in `~/Documents/4xForecaster/hurst-agent/src/hurst_agent/cycles.py`.
    No smoothing by default (Hurst canonical uses raw median).
    """
    mp = median_price(df)
    if smooth > 1:
        mp = mp.rolling(smooth, min_periods=1).mean()
    shift = cycle_bars // 2 + 1   # canonical Hurst shift
    return mp.shift(shift).rename(f"fld_{cycle_bars}")


def fld_bias(df: pd.DataFrame, cycles=DEFAULT_CYCLES, close_col: str = "close") -> pd.DataFrame:
    """Compute multi-cycle FLD bias.

    Returns a DataFrame indexed like df with columns:
      fld_<N>          the FLD level for each cycle
      bias_<N>         +1 (price>FLD) / 0 (price=FLD) / -1 (price<FLD)
      bias_agree       count of cycles where bias=+1 (0..len(cycles))
      bias_label       'bullish' / 'bearish' / 'neutral'
    """
    out = pd.DataFrame(index=df.index)
    for N in cycles:
        fld = compute_fld(df, N)
        out[f"fld_{N}"] = fld
        diff = df[close_col] - fld
        out[f"bias_{N}"] = np.where(diff > 0, 1, np.where(diff < 0, -1, 0))
    bull_count = sum(out[f"bias_{N}"] == 1 for N in cycles)
    out["bias_agree"] = bull_count
    out["bias_label"] = np.where(
        bull_count == len(cycles), "bullish",
        np.where(bull_count == 0, "bearish", "neutral"),
    )
    # Mark NaN where any FLD is undefined (not enough history)
    nan_mask = out[[f"fld_{N}" for N in cycles]].isna().any(axis=1)
    out.loc[nan_mask, "bias_label"] = "unknown"
    return out
