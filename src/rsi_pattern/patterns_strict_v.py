"""Strict V — symmetric mirror of `patterns_strict.detect_strict_m`.

Same topology, flipped vertically about RSI=50:

  M (top):   rise from <30 → peaks ≥72 → wiggle stays ≥72 → fall <50
  V (bot):   fall from >70 → troughs ≤28 → wiggle stays ≤28 → rise >50

Implementation strategy: invert the RSI series (rsi' = 100 - rsi) and
reuse the strict-M detector. Then convert each detected M on the inverted
series back to a V on the original.

Why this exists:
- H20 showed Scheme A (no FLD scaling) beats Scheme C on 1h test data —
  the LONG-side bearish-FLD amplifier is weakening.
- H15 showed USDCHF NO-GO on long-only because its FLD bias is bullish-
  skewed (long-side bearish-FLD bucket is under-fed).
- A symmetric SHORT path captures setups the long-only system misses
  AND has a structurally larger high-conviction bucket on bullish-FLD-
  skewed symbols.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd

from .patterns_strict import StrictPatternConfig, StrictM, detect_strict_m


@dataclass
class StrictVConfig:
    """Mirror of StrictPatternConfig flipped about RSI=50.

    Defaults map H14's strict-M calibration (30, 72, 72, 50) symmetrically:
      fall_origin_above   = 100 - rise_origin_below   = 70
      major_trough_max    = 100 - major_peak_min      = 28
      wiggle_peak_ceiling = 100 - wiggle_trough_floor = 28
      completion_threshold = 50                        (same; the midline)
    Bar caps unchanged.
    """
    fall_origin_above: float = 70.0
    major_trough_max: float = 28.0
    wiggle_peak_ceiling: float = 28.0
    completion_threshold: float = 50.0
    max_fall_bars: int = 60
    max_bottom_zone_bars: int = 60
    max_completion_bars: int = 60
    min_peak_prominence: float = 1.0
    min_peak_distance_bars: int = 2


@dataclass
class StrictV:
    """Mirror of StrictM. Field-name semantics flipped: peak→trough, rise→fall."""
    fall_start_idx: int
    first_major_trough_idx: int     # T1 — first bar where RSI ≤ major_trough_max
    last_major_trough_idx: int      # T2 — final trough in bottom zone
    completion_idx: Optional[int]   # bar where RSI breaks above completion_threshold
    n_wiggle_troughs: int
    fall_bars: int                  # bars from fall_start to first_major_trough
    fall_velocity: float            # RSI points/bar (negative — falling)
    trough_min: float
    inner_peak_max: float


def detect_strict_v(rsi: pd.Series,
                    cfg: Optional[StrictVConfig] = None) -> list[StrictV]:
    """Detect strict-V patterns by reusing the strict-M detector on inverted RSI.

    inverted_rsi = 100 - rsi
    A trough at RSI=25 becomes a peak at inv_rsi=75 → detect_strict_m sees it as
    a major peak. The thresholds flip arithmetically (see StrictVConfig docstring).
    """
    cfg = cfg or StrictVConfig()
    inv = 100.0 - rsi
    inv_cfg = StrictPatternConfig(
        rise_origin_below=100.0 - cfg.fall_origin_above,
        major_peak_min=100.0 - cfg.major_trough_max,
        wiggle_trough_floor=100.0 - cfg.wiggle_peak_ceiling,
        completion_threshold=100.0 - cfg.completion_threshold,
        max_rise_bars=cfg.max_fall_bars,
        max_top_zone_bars=cfg.max_bottom_zone_bars,
        max_completion_bars=cfg.max_completion_bars,
        min_peak_prominence=cfg.min_peak_prominence,
        min_peak_distance_bars=cfg.min_peak_distance_bars,
    )
    rsi_arr = rsi.to_numpy()
    out: list[StrictV] = []
    for m in detect_strict_m(inv, inv_cfg):
        # Convert StrictM on inverted series back to StrictV on original.
        # Positions are identical (same index); only the values invert.
        fall_start = int(m.rise_start_idx)
        t1 = int(m.first_major_peak_idx)
        t2 = int(m.last_major_peak_idx)
        comp = int(m.completion_idx) if m.completion_idx is not None else None
        # peak_max on inverted ≡ 100 - trough_min on original
        trough_min = float(100.0 - m.peak_max)
        # inner_trough_min on inverted ≡ 100 - inner_peak_max on original
        inner_peak_max = float(100.0 - m.inner_trough_min)
        out.append(StrictV(
            fall_start_idx=fall_start,
            first_major_trough_idx=t1,
            last_major_trough_idx=t2,
            completion_idx=comp,
            n_wiggle_troughs=int(m.n_wiggle_peaks),
            fall_bars=int(m.rise_bars),
            fall_velocity=float(-m.rise_velocity),  # negate sign: falling
            trough_min=trough_min,
            inner_peak_max=inner_peak_max,
        ))
    return out
