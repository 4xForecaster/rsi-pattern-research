"""Statistical validation: detection quality, fractal self-similarity, forward returns,
state-transition predictability."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats


def state_occupancy(states: pd.Series) -> pd.Series:
    """% of bars in each state."""
    return states.value_counts(normalize=True).sort_index()


def state_durations(states: pd.Series, freq: str | None = None) -> pd.DataFrame:
    """Return one row per state-run: state, start_idx, end_idx, length_bars, length_time."""
    changes = (states != states.shift()).cumsum()
    grouped = states.groupby(changes)
    rows = []
    for _, g in grouped:
        rows.append({
            "state": g.iloc[0],
            "start": g.index[0],
            "end": g.index[-1],
            "length_bars": len(g),
            "length_seconds": (g.index[-1] - g.index[0]).total_seconds() if len(g) > 1 else 0,
        })
    return pd.DataFrame(rows)


def transition_matrix(states: pd.Series) -> pd.DataFrame:
    """Empirical state transition probabilities (P(s_{t+1} | s_t))."""
    pairs = pd.DataFrame({
        "from": states[:-1].values,
        "to": states[1:].values,
    })
    counts = pairs.groupby(["from", "to"]).size().unstack(fill_value=0)
    # Normalize rows
    return counts.div(counts.sum(axis=1), axis=0).fillna(0)


def fractal_compare(
    states_by_tf: dict[str, pd.Series],
) -> dict:
    """H2 — Fractal self-similarity test.

    Compare state-occupancy, mean state durations (in calendar time, NOT bars),
    and transition matrices across timeframes. Returns a dict of statistical
    tests for each pairwise comparison.
    """
    out: dict = {"occupancy": {}, "transition_chi2": {}, "duration_ks": {}}

    occupancies = {tf: state_occupancy(s) for tf, s in states_by_tf.items()}
    out["occupancy"] = pd.DataFrame(occupancies).fillna(0)

    durations = {tf: state_durations(s) for tf, s in states_by_tf.items()}

    tfs = list(states_by_tf.keys())
    for i in range(len(tfs)):
        for j in range(i + 1, len(tfs)):
            tf_a, tf_b = tfs[i], tfs[j]
            # KS test on calendar-time durations per state
            for state in ["M", "C", "V"]:
                a = durations[tf_a].query("state == @state")["length_seconds"]
                b = durations[tf_b].query("state == @state")["length_seconds"]
                if len(a) >= 5 and len(b) >= 5:
                    ks = stats.ks_2samp(a, b)
                    out["duration_ks"][f"{tf_a}_vs_{tf_b}_{state}"] = {
                        "statistic": float(ks.statistic),
                        "pvalue": float(ks.pvalue),
                    }

            # Chi-squared on transition matrices
            tm_a = transition_matrix(states_by_tf[tf_a])
            tm_b = transition_matrix(states_by_tf[tf_b])
            # Align columns/rows
            all_states = sorted(set(tm_a.index) | set(tm_b.index))
            tm_a = tm_a.reindex(index=all_states, columns=all_states, fill_value=0)
            tm_b = tm_b.reindex(index=all_states, columns=all_states, fill_value=0)
            obs_a = (tm_a.values * 1000).round().astype(int) + 1  # avoid zeros
            obs_b = (tm_b.values * 1000).round().astype(int) + 1
            try:
                chi2, p, _, _ = stats.chi2_contingency(np.vstack([obs_a.flatten(), obs_b.flatten()]))
                out["transition_chi2"][f"{tf_a}_vs_{tf_b}"] = {
                    "chi2": float(chi2),
                    "pvalue": float(p),
                }
            except ValueError:
                pass

    return out


def m_lifecycle_stats(df: pd.DataFrame, rsi_col: str = "rsi14", cfg=None) -> dict:
    """Duration and amplitude statistics for completed M patterns.

    Duration = bars from P1 to completion (RSI cross below 50).
    Amplitude = max(peak_RSI) - min(dip_RSI) within the M, in RSI units.

    Returns a dict of (durations, amplitudes, summary) for all completed Ms.
    """
    from .patterns import detect_m, PatternConfig
    cfg = cfg or PatternConfig()
    rsi = df[rsi_col].dropna()
    rsi_arr = rsi.to_numpy()
    durations, amplitudes = [], []
    for p in detect_m(rsi, cfg):
        if p.completed_idx is None:
            continue
        p1, p2 = p.anchors
        comp = p.completed_idx
        dip_level = float(rsi_arr[p1:p2 + 1].min())
        peak_level = float(max(rsi_arr[p1], rsi_arr[p2]))
        durations.append(comp - p1)
        amplitudes.append(peak_level - dip_level)
    return {
        "n_patterns": len(durations),
        "duration_bars": {
            "mean": float(np.mean(durations)) if durations else 0,
            "median": float(np.median(durations)) if durations else 0,
            "std": float(np.std(durations)) if durations else 0,
            "values": durations,
        },
        "amplitude_rsi": {
            "mean": float(np.mean(amplitudes)) if amplitudes else 0,
            "median": float(np.median(amplitudes)) if amplitudes else 0,
            "std": float(np.std(amplitudes)) if amplitudes else 0,
            "values": amplitudes,
        },
    }


def v_lifecycle_stats(df: pd.DataFrame, rsi_col: str = "rsi14", cfg=None) -> dict:
    """Mirror of m_lifecycle_stats for V patterns."""
    from .patterns import detect_v, PatternConfig
    cfg = cfg or PatternConfig()
    rsi = df[rsi_col].dropna()
    rsi_arr = rsi.to_numpy()
    durations, amplitudes = [], []
    for p in detect_v(rsi, cfg):
        if p.completed_idx is None:
            continue
        t1, t2 = p.anchors
        comp = p.completed_idx
        peak_level = float(rsi_arr[t1:t2 + 1].max())
        trough_level = float(min(rsi_arr[t1], rsi_arr[t2]))
        durations.append(comp - t1)
        amplitudes.append(peak_level - trough_level)
    return {
        "n_patterns": len(durations),
        "duration_bars": {
            "mean": float(np.mean(durations)) if durations else 0,
            "median": float(np.median(durations)) if durations else 0,
            "std": float(np.std(durations)) if durations else 0,
            "values": durations,
        },
        "amplitude_rsi": {
            "mean": float(np.mean(amplitudes)) if amplitudes else 0,
            "median": float(np.median(amplitudes)) if amplitudes else 0,
            "std": float(np.std(amplitudes)) if amplitudes else 0,
            "values": amplitudes,
        },
    }


def trough_breach_signals(
    df: pd.DataFrame,
    rsi_col: str = "rsi14",
    cfg=None,
) -> dict[str, list[dict]]:
    """Detect three structural breach signals:

    - 'm_dip_breach': RSI breaks below the inner dip between P1 and P2 (after P2).
      EMPIRICALLY a LONG signal on DXY (forward returns positive at 5-20 bar horizons).
    - 'm_bottom_breach': RSI breaks below the M's structural floor (min of trough-before-P1
      and trough-after-P2). Weak SHORT signal at 20+ bar horizons (d ≈ -0.2 to -0.4).
    - 'v_floor_breach': RSI breaks below V's floor (min of T1, T2 levels). STRONG SHORT
      signal across all timeframes (d ≈ -1.5 on daily 20-bar).

    Returns {signal_name: list of {signal_idx, ...metadata}}.
    See results/H3_trough_breach.md for empirical analysis.
    """
    from .patterns import detect_m, detect_v, PatternConfig
    from scipy.signal import find_peaks

    cfg = cfg or PatternConfig()
    rsi = df[rsi_col].dropna()
    rsi_arr = rsi.to_numpy()
    n = len(rsi_arr)

    trough_idx, _ = find_peaks(
        -rsi_arr,
        prominence=cfg.min_peak_prominence,
        distance=cfg.min_peak_distance_bars,
    )

    signals: dict[str, list[dict]] = {
        "m_dip_breach": [],
        "m_bottom_breach": [],
        "v_floor_breach": [],
    }

    for p in detect_m(rsi, cfg):
        if p.completed_idx is None:
            continue
        p1, p2 = p.anchors
        dip_level = float(rsi_arr[p1:p2 + 1].min())
        # m_dip_breach: first bar after P2 where RSI < dip_level
        for i in range(p2 + 1, min(p2 + 200, n)):
            if rsi_arr[i] < dip_level:
                signals["m_dip_breach"].append({
                    "signal_idx": i, "P1": p1, "P2": p2, "dip_level": dip_level,
                })
                break
        # m_bottom_breach: outer floor
        before_t = trough_idx[trough_idx < p1]
        after_t = trough_idx[trough_idx > p2]
        if len(before_t) and len(after_t):
            prev_t, post_t = int(before_t[-1]), int(after_t[0])
            m_bottom = min(float(rsi_arr[prev_t]), float(rsi_arr[post_t]))
            for i in range(post_t + 1, min(post_t + 200, n)):
                if rsi_arr[i] < m_bottom:
                    signals["m_bottom_breach"].append({
                        "signal_idx": i, "P1": p1, "P2": p2,
                        "prev_trough": prev_t, "post_trough": post_t,
                        "m_bottom_level": m_bottom,
                    })
                    break

    for p in detect_v(rsi, cfg):
        if p.completed_idx is None:
            continue
        t1, t2 = p.anchors
        floor_level = float(min(rsi_arr[t1], rsi_arr[t2]))
        for i in range(t2 + 1, min(t2 + 200, n)):
            if rsi_arr[i] < floor_level:
                signals["v_floor_breach"].append({
                    "signal_idx": i, "T1": t1, "T2": t2, "floor_level": floor_level,
                })
                break

    return signals


def event_conditional_returns(
    df: pd.DataFrame,
    states: pd.Series,
    horizons_bars: tuple[int, ...] = (1, 5, 20, 60),
    close_col: str = "close",
) -> pd.DataFrame:
    """H3 — Forward returns conditional on TRANSITION events (not occupancy).

    For each pair (prev_state -> curr_state) where state changes, compute
    forward returns over K bars and compare to unconditional baseline.

    This is the test that produces the large directional effects on DXY.
    C->M and C->V transitions (first peak / first trough) show Cohen's d ~1.0
    across all timeframes at the 1-bar horizon. See results/H3_event_conditional.md.
    """
    log_close = np.log(df[close_col])
    prev = states.shift(1)
    curr = states

    # Only enumerate transitions that actually occur (skip M<->V which never do)
    event_masks = {}
    for src in ["C", "M", "V"]:
        for dst in ["C", "M", "V"]:
            if src == dst:
                continue
            mask = (prev == src) & (curr == dst)
            if mask.sum() > 0:
                event_masks[f"{src}->{dst}"] = mask

    rows = []
    for K in horizons_bars:
        fwd = log_close.shift(-K) - log_close
        baseline = fwd.dropna()
        baseline_mean = float(baseline.mean())
        for event_name, mask in event_masks.items():
            cond = fwd[mask].dropna()
            if len(cond) < 10:
                continue
            ks = stats.ks_2samp(cond, baseline)
            t_stat, t_p = stats.ttest_ind(cond, baseline, equal_var=False)
            pooled = np.sqrt((cond.var() + baseline.var()) / 2)
            d = (cond.mean() - baseline_mean) / pooled if pooled > 0 else 0
            rows.append({
                "event": event_name,
                "horizon_bars": K,
                "n": len(cond),
                "mean_return": float(cond.mean()),
                "baseline_mean": baseline_mean,
                "diff": float(cond.mean() - baseline_mean),
                "cohens_d": float(d),
                "t_pvalue": float(t_p),
                "ks_pvalue": float(ks.pvalue),
            })
    return pd.DataFrame(rows)


def conditional_forward_returns(
    df: pd.DataFrame,
    states: pd.Series,
    horizons_bars: tuple[int, ...] = (1, 5, 20, 60),
    close_col: str = "close",
) -> pd.DataFrame:
    """H3 — Conditional forward returns by state.

    For each completed state run, compute the K-bar forward log-return of the
    underlying price. Compare conditional distribution to unconditional baseline.
    """
    log_close = np.log(df[close_col])
    rows = []
    for K in horizons_bars:
        fwd_ret = (log_close.shift(-K) - log_close)
        unconditional_mean = float(fwd_ret.mean())
        unconditional_std = float(fwd_ret.std())
        for state in sorted(states.dropna().unique()):
            mask = states == state
            cond = fwd_ret[mask].dropna()
            if len(cond) < 10:
                continue
            # KS vs unconditional
            unconditional = fwd_ret.dropna()
            ks = stats.ks_2samp(cond, unconditional)
            # Cohen's d
            pooled_std = np.sqrt((cond.std() ** 2 + unconditional_std ** 2) / 2)
            cohens_d = (cond.mean() - unconditional_mean) / pooled_std if pooled_std > 0 else 0
            rows.append({
                "state": state,
                "horizon_bars": K,
                "n": len(cond),
                "mean_return": float(cond.mean()),
                "std_return": float(cond.std()),
                "ks_statistic": float(ks.statistic),
                "ks_pvalue": float(ks.pvalue),
                "cohens_d": float(cohens_d),
            })
    return pd.DataFrame(rows)
