"""M / C / V pattern detection on RSI oscillator.

See docs/PATTERN_DEFINITIONS.md for the formal definitions and the open
question on C's exact topology (candidate (a) vs (b)). Defaults below
use candidate (a) — C is the traversal phase between completed M and V.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Iterable
import numpy as np
import pandas as pd
from scipy.signal import find_peaks


@dataclass
class PatternConfig:
    """Tunable thresholds. Defaults are starting values."""

    # M (top) thresholds
    m_peak_threshold: float = 65.0
    m_inner_threshold: float = 50.0
    m_completion_threshold: float = 50.0

    # V (bottom) thresholds
    v_trough_threshold: float = 35.0
    v_inner_threshold: float = 50.0
    v_completion_threshold: float = 50.0

    # Timing (in bars — tune per timeframe)
    max_span_bars: int = 30
    max_completion_bars: int = 30
    min_peak_prominence: float = 3.0
    min_peak_distance_bars: int = 3

    # C definition: (a) = traversal, (b) = explicit shape
    c_definition: Literal["a", "b"] = "a"


@dataclass
class Pattern:
    kind: Literal["M", "V", "C"]
    anchors: tuple[int, ...]  # bar indices defining the shape
    completed_idx: int | None = None  # bar index where shape "completed"
    confidence: float = 1.0  # 0..1; placeholder for later refinement


def _find_peaks_troughs(
    rsi: pd.Series, cfg: PatternConfig
) -> tuple[np.ndarray, np.ndarray]:
    """Return (peak_indices, trough_indices) of the RSI series."""
    rsi_arr = rsi.to_numpy()
    peak_idx, _ = find_peaks(
        rsi_arr,
        prominence=cfg.min_peak_prominence,
        distance=cfg.min_peak_distance_bars,
    )
    trough_idx, _ = find_peaks(
        -rsi_arr,
        prominence=cfg.min_peak_prominence,
        distance=cfg.min_peak_distance_bars,
    )
    return peak_idx, trough_idx


def detect_m(rsi: pd.Series, cfg: PatternConfig | None = None) -> list[Pattern]:
    """Detect all M (top) patterns in the RSI series.

    An M requires two peaks both above `m_peak_threshold`, dip between them
    above `m_inner_threshold`, and a subsequent break below `m_completion_threshold`.
    """
    cfg = cfg or PatternConfig()
    rsi_arr = rsi.to_numpy()
    peak_idx, _ = _find_peaks_troughs(rsi, cfg)

    out: list[Pattern] = []
    n = len(rsi_arr)

    for i in range(len(peak_idx) - 1):
        p1, p2 = int(peak_idx[i]), int(peak_idx[i + 1])
        if p2 - p1 > cfg.max_span_bars:
            continue
        if rsi_arr[p1] < cfg.m_peak_threshold or rsi_arr[p2] < cfg.m_peak_threshold:
            continue
        dip = float(np.min(rsi_arr[p1:p2 + 1]))
        if dip < cfg.m_inner_threshold:
            continue
        # Look for completion: RSI crossing below completion_threshold within max_completion_bars
        end = min(p2 + cfg.max_completion_bars + 1, n)
        post = rsi_arr[p2:end]
        below = np.where(post < cfg.m_completion_threshold)[0]
        completed_idx = int(p2 + below[0]) if below.size > 0 else None
        out.append(Pattern(kind="M", anchors=(p1, p2), completed_idx=completed_idx))

    return out


def detect_v(rsi: pd.Series, cfg: PatternConfig | None = None) -> list[Pattern]:
    """Detect all V (bottom) patterns in the RSI series. Mirror of detect_m."""
    cfg = cfg or PatternConfig()
    rsi_arr = rsi.to_numpy()
    _, trough_idx = _find_peaks_troughs(rsi, cfg)

    out: list[Pattern] = []
    n = len(rsi_arr)

    for i in range(len(trough_idx) - 1):
        t1, t2 = int(trough_idx[i]), int(trough_idx[i + 1])
        if t2 - t1 > cfg.max_span_bars:
            continue
        if rsi_arr[t1] > cfg.v_trough_threshold or rsi_arr[t2] > cfg.v_trough_threshold:
            continue
        peak = float(np.max(rsi_arr[t1:t2 + 1]))
        if peak > cfg.v_inner_threshold:
            continue
        end = min(t2 + cfg.max_completion_bars + 1, n)
        post = rsi_arr[t2:end]
        above = np.where(post > cfg.v_completion_threshold)[0]
        completed_idx = int(t2 + above[0]) if above.size > 0 else None
        out.append(Pattern(kind="V", anchors=(t1, t2), completed_idx=completed_idx))

    return out


def label_states(
    rsi: pd.Series,
    m_patterns: Iterable[Pattern],
    v_patterns: Iterable[Pattern],
    cfg: PatternConfig | None = None,
) -> pd.Series:
    """Assign a state label to every bar.

    Under cfg.c_definition='a' (default): every bar is M, V, or C.
    - 'M' = within an M pattern from P1 to completion
    - 'V' = within a V pattern from T1 to completion
    - 'C' = everything else
    """
    cfg = cfg or PatternConfig()
    n = len(rsi)
    state = np.full(n, "C", dtype="<U1")

    for p in m_patterns:
        start = p.anchors[0]
        end = (p.completed_idx if p.completed_idx is not None else p.anchors[-1]) + 1
        state[start:end] = "M"

    for p in v_patterns:
        start = p.anchors[0]
        end = (p.completed_idx if p.completed_idx is not None else p.anchors[-1]) + 1
        state[start:end] = "V"

    if cfg.c_definition == "b":
        # Reserved for the candidate-(b) topology; not implemented in v0.
        # Bars currently labeled 'C' would need further filtering against a
        # specific C shape definition.
        pass

    return pd.Series(state, index=rsi.index, name="state")


def detect_all(
    df: pd.DataFrame, cfg: PatternConfig | None = None, rsi_col: str = "rsi14"
) -> pd.DataFrame:
    """Run full detection and return df with a 'state' column appended.

    Expects df to already have an RSI column (default 'rsi14').
    """
    cfg = cfg or PatternConfig()
    if rsi_col not in df.columns:
        raise KeyError(f"{rsi_col!r} not found in df. Run indicators.add_rsi first.")
    rsi = df[rsi_col].dropna()
    m_patterns = detect_m(rsi, cfg)
    v_patterns = detect_v(rsi, cfg)
    state = label_states(rsi, m_patterns, v_patterns, cfg)
    out = df.copy()
    out["state"] = state.reindex(df.index, fill_value="C")
    return out


def summarize(states: pd.Series) -> dict:
    """Quick state statistics — occupancy %, mean run length, transition counts."""
    states = states.dropna()
    occupancy = states.value_counts(normalize=True).to_dict()

    # Run-length encoding for durations
    changes = (states != states.shift()).cumsum()
    runs = states.groupby(changes).agg(["first", "size"]).reset_index(drop=True)
    runs.columns = ["state_label", "length"]
    mean_run_by_state = runs.groupby("state_label")["length"].mean().to_dict()

    # Transition counts
    next_state = states.shift(-1).dropna()
    pairs = pd.DataFrame({"from": states[:-1].values, "to": next_state.values})
    transitions = pairs.groupby(["from", "to"]).size().unstack(fill_value=0)

    return {
        "occupancy_pct": occupancy,
        "mean_run_length_bars": mean_run_by_state,
        "transitions": transitions,
    }
