"""Strict M definition (user-specified, 2026-05-12).

Differences from `patterns.detect_m`:
- Origin requirement: RSI must rise FROM below 30 to ≥75.01 within the rise leg
- Strict peak threshold: ≥75.01 at close (not 65+)
- Inner trough threshold: ≥70 (allows "wiggle" peaks/troughs in upper zone)
- Multi-peak topology supported: any number of peaks ≥75.01 in the upper zone
  before completion, as long as inner troughs stay ≥70

Also tracks rate-of-change of the rise leg (RSI delta per bar from origin
to first ≥75.01 peak) — the user-flagged feature for M pre-qualification.

Strict-M is much rarer than loose-M, expected to have higher signal-to-noise.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd
from scipy.signal import find_peaks


@dataclass
class StrictPatternConfig:
    rise_origin_below: float = 30.0
    major_peak_min: float = 75.01
    wiggle_trough_floor: float = 70.0
    completion_threshold: float = 50.0
    max_rise_bars: int = 60          # cap on how long the rising leg can take
    max_top_zone_bars: int = 60      # cap on how long the upper-zone wiggle can last
    max_completion_bars: int = 60    # cap from last peak to break-below-50
    min_peak_prominence: float = 1.0
    min_peak_distance_bars: int = 2


@dataclass
class StrictM:
    rise_start_idx: int              # first bar of the rise leg (RSI cross down<30 most recent)
    first_major_peak_idx: int        # first bar with close RSI ≥75.01
    last_major_peak_idx: int         # final peak in top zone before fall
    completion_idx: Optional[int]    # bar where RSI breaks below 50
    n_wiggle_peaks: int              # how many ≥75.01 peaks (1 = no wiggle)
    rise_bars: int                   # bars from rise_start to first_major_peak
    rise_velocity: float             # RSI points per bar on the rise leg
    peak_max: float                  # highest RSI in the M
    inner_trough_min: float          # lowest RSI in upper zone (between major peaks)


def detect_strict_m(rsi: pd.Series, cfg: StrictPatternConfig | None = None) -> list[StrictM]:
    """Detect M patterns by strict topology.

    Algorithm:
      1. Find all bars where RSI ≥ major_peak_min (75.01) at close.
      2. Group consecutive close-≥-75.01 episodes into "top zone visits".
         Adjacent top-zone visits separated by intervening RSI staying ≥
         wiggle_trough_floor (70) are considered ONE M (wiggle).
      3. For each grouped top-zone, find the most recent prior bar where
         RSI dropped below rise_origin_below (30). That's rise_start.
      4. M completes when RSI drops below completion_threshold (50) after
         the last major peak.
    """
    cfg = cfg or StrictPatternConfig()
    rsi_arr = rsi.to_numpy()
    n = len(rsi_arr)

    # Step 1: identify all major-peak bars (RSI ≥ 75.01)
    major = rsi_arr >= cfg.major_peak_min
    if not major.any():
        return []

    # Step 2: group adjacent top-zone visits into M candidates
    # An M candidate spans from first major peak to last major peak, allowing
    # the in-between RSI to dip into the wiggle floor [70, 75.01) without
    # breaking the group.
    groups: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if not major[i]:
            i += 1
            continue
        group_start = i
        last_major = i
        # Extend group: keep going while RSI stays ≥ wiggle_trough_floor (70)
        j = i + 1
        while j < n and rsi_arr[j] >= cfg.wiggle_trough_floor:
            if major[j]:
                last_major = j
            j += 1
        groups.append((group_start, last_major))
        i = j + 1

    out: list[StrictM] = []
    for group_start, group_end in groups:
        # Step 3: find rise_start = most recent bar BEFORE group_start where RSI < 30
        rise_start = None
        for k in range(group_start - 1, max(group_start - cfg.max_rise_bars - 1, -1), -1):
            if rsi_arr[k] < cfg.rise_origin_below:
                rise_start = k
                break
        if rise_start is None:
            # Did not originate from below 30 within max_rise_bars — skip
            continue

        rise_bars = group_start - rise_start
        if rise_bars <= 0 or rise_bars > cfg.max_rise_bars:
            continue
        rise_velocity = (rsi_arr[group_start] - rsi_arr[rise_start]) / rise_bars

        # Step 4: find completion (RSI < 50 after group_end)
        completion = None
        end_look = min(group_end + cfg.max_completion_bars + 1, n)
        for k in range(group_end + 1, end_look):
            if rsi_arr[k] < cfg.completion_threshold:
                completion = k
                break

        # Inner trough min (lowest RSI in upper zone between major peaks)
        if group_end > group_start:
            inner_trough_min = float(rsi_arr[group_start:group_end + 1].min())
        else:
            inner_trough_min = float(rsi_arr[group_start])

        # Count of distinct major peaks within the group (using find_peaks)
        if group_end - group_start >= 2:
            peaks_in_group, _ = find_peaks(
                rsi_arr[group_start:group_end + 1],
                height=cfg.major_peak_min,
                distance=cfg.min_peak_distance_bars,
            )
            n_wiggle = len(peaks_in_group)
            if n_wiggle == 0:
                n_wiggle = 1
        else:
            n_wiggle = 1

        out.append(StrictM(
            rise_start_idx=rise_start,
            first_major_peak_idx=group_start,
            last_major_peak_idx=group_end,
            completion_idx=completion,
            n_wiggle_peaks=n_wiggle,
            rise_bars=rise_bars,
            rise_velocity=rise_velocity,
            peak_max=float(rsi_arr[group_start:group_end + 1].max()),
            inner_trough_min=inner_trough_min,
        ))

    return out
