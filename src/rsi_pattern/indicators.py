"""Technical indicators — Welles Wilder's RSI(14) using Wilder smoothing (RMA)."""
from __future__ import annotations
import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Welles Wilder RSI using Wilder's smoothing (RMA, equivalent to EMA with alpha=1/period).

    This is the canonical RSI as defined by Wilder in 'New Concepts in Technical
    Trading Systems' (1978). Differs from SMA-based RSI variants which produce
    slightly different oscillation profiles.
    """
    if period < 2:
        raise ValueError("period must be >= 2")

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder smoothing == EMA with alpha = 1/period, adjust=False
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out.name = f"rsi{period}"
    return out


def add_rsi(df: pd.DataFrame, period: int = 14, col: str = "close") -> pd.DataFrame:
    """Append an RSI column to a DataFrame; returns a new DataFrame."""
    out = df.copy()
    out[f"rsi{period}"] = rsi(out[col], period=period)
    return out
