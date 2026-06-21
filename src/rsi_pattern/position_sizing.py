"""Position sizing + SURF-style Fibonacci targets + 3-bar trailing stop.

Per Dr. A's specification (2026-05-12):

The RANGE is defined by the price corresponding to the RSI pattern's
highest-high and the subsequent lowest-low in price. Fibonacci targets
are projected at 1.618x, 2.236x, and 3.618x that range, in the direction
of the trade.

A 3-bar trailing stop activates as price approaches the final target.
The stop is placed at the low of the last 3 higher-high bars
(excluding inside bars) for long trades; mirror for shorts.

Note: Interpretation is provisional. Dr. A's "RSI & Ghost Patterns"
repo (private) may have a more precise definition of how the range is
anchored to RSI peaks/troughs. This implementation uses the M-pattern's
P1-to-completion price excursion as the reference range for long trades,
and the V-pattern's peak-to-trough price excursion for short trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
import numpy as np
import pandas as pd

from .patterns import detect_m, detect_v, PatternConfig

FIB_LEVELS = (1.618, 2.236, 3.618)  # T1, T2, T3 multipliers


@dataclass
class FibTrade:
    direction: Literal["long", "short"]
    entry_idx: int
    entry_price: float
    range_size: float                  # absolute price units
    range_high_idx: int                # bar index of the range's high
    range_low_idx: int                 # bar index of the range's low
    initial_stop: float                # initial structural stop price
    targets: list[float]               # T1, T2, T3 absolute prices
    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""              # "T1" / "T2" / "T3" / "stop" / "time"

    @property
    def risk(self) -> float:
        """Absolute price risk per unit at entry."""
        return abs(self.entry_price - self.initial_stop)

    @property
    def gross_return(self) -> Optional[float]:
        if self.exit_price is None:
            return None
        if self.direction == "long":
            return np.log(self.exit_price) - np.log(self.entry_price)
        return np.log(self.entry_price) - np.log(self.exit_price)

    @property
    def r_multiple(self) -> Optional[float]:
        """Return as multiple of initial risk (R)."""
        if self.exit_price is None or self.risk == 0:
            return None
        gain = (self.exit_price - self.entry_price) if self.direction == "long" \
               else (self.entry_price - self.exit_price)
        return gain / self.risk


def define_fib_range_long(df: pd.DataFrame, p1_idx: int, completion_idx: Optional[int],
                          high_col: str = "high", low_col: str = "low") -> tuple[float, int, int]:
    """For a LONG entry at P1+1 on an M pattern, define the reference range
    as the price excursion of the rise leg PLUS the M's local fall.

    Range = high(P1) - low(rise_origin region)
    The reference 'low' is the most recent price low BEFORE P1 (the prior V's
    bottom or local price floor).
    """
    n = len(df)
    if p1_idx <= 0:
        return 0.0, 0, p1_idx
    # Lookback for the local price low before P1
    lookback = min(p1_idx, 60)
    seg = df.iloc[p1_idx - lookback:p1_idx]
    low_idx = int(seg[low_col].idxmin().to_pydatetime().timestamp() if False else seg[low_col].argmin() + (p1_idx - lookback))
    # Simpler integer-position approach:
    low_pos = (df.iloc[p1_idx - lookback:p1_idx][low_col].values).argmin() + (p1_idx - lookback)
    price_low = float(df[low_col].iloc[low_pos])
    price_high = float(df[high_col].iloc[p1_idx])
    range_size = price_high - price_low
    return range_size, p1_idx, low_pos


def define_fib_range_short(df: pd.DataFrame, t2_idx: int, breach_idx: int,
                            high_col: str = "high", low_col: str = "low") -> tuple[float, int, int]:
    """For a SHORT entry on V-floor breach, define the reference range as
    the V's price height: the local price high before/within V minus the
    V's lowest price.
    """
    n = len(df)
    if breach_idx <= 0:
        return 0.0, 0, breach_idx
    # Lookback for the local price high before V's floor breach
    lookback = min(breach_idx, 60)
    seg = df.iloc[breach_idx - lookback:breach_idx]
    high_pos = (df.iloc[breach_idx - lookback:breach_idx][high_col].values).argmax() + (breach_idx - lookback)
    # Low is the V's floor (or the breach bar's low)
    low_pos = (df.iloc[breach_idx - lookback:breach_idx][low_col].values).argmin() + (breach_idx - lookback)
    price_high = float(df[high_col].iloc[high_pos])
    price_low = float(df[low_col].iloc[low_pos])
    range_size = price_high - price_low
    return range_size, high_pos, low_pos


def compute_fib_targets(entry_price: float, range_size: float,
                         direction: Literal["long", "short"]) -> list[float]:
    """Return T1, T2, T3 absolute prices."""
    if direction == "long":
        return [entry_price + lvl * range_size for lvl in FIB_LEVELS]
    return [entry_price - lvl * range_size for lvl in FIB_LEVELS]


def three_bar_trailing_stop_long(df: pd.DataFrame, start_idx: int, current_idx: int,
                                  low_col: str = "low", high_col: str = "high") -> float:
    """Return the trailing stop level (long position) at current_idx.

    Stop = low of the last 3 bars where the bar made a higher-high,
    EXCLUDING inside bars (high < prev_high AND low > prev_low).
    """
    # Walk back from current_idx
    higher_high_bars = []
    last_high = -np.inf
    for i in range(start_idx, current_idx + 1):
        h, l = df[high_col].iloc[i], df[low_col].iloc[i]
        if i > start_idx:
            prev_h = df[high_col].iloc[i - 1]
            prev_l = df[low_col].iloc[i - 1]
            # Inside bar?
            if h < prev_h and l > prev_l:
                continue
        if h > last_high:
            higher_high_bars.append((i, l))
            last_high = h
    if len(higher_high_bars) < 3:
        return -np.inf
    last3_lows = [low for (_, low) in higher_high_bars[-3:]]
    return float(min(last3_lows))


def three_bar_trailing_stop_short(df: pd.DataFrame, start_idx: int, current_idx: int,
                                   low_col: str = "low", high_col: str = "high") -> float:
    """Mirror of trailing-stop-long for short positions.
    Stop = high of the last 3 lower-low bars, excluding inside bars."""
    lower_low_bars = []
    last_low = np.inf
    for i in range(start_idx, current_idx + 1):
        h, l = df[high_col].iloc[i], df[low_col].iloc[i]
        if i > start_idx:
            prev_h = df[high_col].iloc[i - 1]
            prev_l = df[low_col].iloc[i - 1]
            if h < prev_h and l > prev_l:
                continue
        if l < last_low:
            lower_low_bars.append((i, h))
            last_low = l
    if len(lower_low_bars) < 3:
        return np.inf
    last3_highs = [high for (_, high) in lower_low_bars[-3:]]
    return float(max(last3_highs))


TRAIL_ACTIVATION_FACTOR = 3.600   # "as price nears 3.618x" — activate trail near final target


def simulate_fib_trade(df: pd.DataFrame, trade: FibTrade,
                        max_bars: int = 200,
                        trail_activation_factor: float = TRAIL_ACTIVATION_FACTOR,
                        trail_activation_price: Optional[float] = None,
                        close_col: str = "close", high_col: str = "high",
                        low_col: str = "low") -> FibTrade:
    """Walk forward bar-by-bar to find the exit.

    Per Dr. A (2026-05-12 clarification): the 3-bar trailing stop activates
    only as price NEARS the FINAL target (at ~3.600x range from entry in the
    M-P1 / Variant B convention). T1, T2 (and intermediate Ts) are markers
    but do NOT trigger a stop adjustment.

    Terminal-exit generalization (2026-06-20, H30 spec tweak): the trade exits
    when ``targets[-1]`` is hit. For canonical 3-target M-P1 / Variant-B
    trades, that's still T3 (unchanged behaviour). For 2-target Variant-A
    box trades it correctly terminates at T2. ``exit_reason`` carries the
    actual final-target name (e.g. "T3" or "T2").

    Trail activation: if ``trail_activation_price`` is given it is used
    directly (this is how box-pattern Variant A passes a price anchored on
    P2 + 2.200·height, mirroring "trail near the final target" when targets
    are NOT entry-anchored). Otherwise it falls back to
    ``entry ± trail_activation_factor · range_size`` (the M-P1 default).

    Logic:
    - Initial stop holds throughout until either:
      - Price hits initial_stop → exit at stop (loss)
      - Price reaches trail-activation price → activate the 3-bar trailing
        stop for the final approach
      - Price reaches the final target cleanly → exit at that target
    - Once trailing stop is active, update each bar; exit when triggered.
    - Hard cap: max_bars (time exit at close).
    """
    n = len(df)
    end = min(trade.entry_idx + max_bars, n)
    targets_hit = []
    stop = trade.initial_stop
    trail_active = False

    # Precompute the trail activation threshold price
    if trail_activation_price is None:
        if trade.direction == "long":
            trail_activation_price = trade.entry_price + trail_activation_factor * trade.range_size
        else:
            trail_activation_price = trade.entry_price - trail_activation_factor * trade.range_size
    final_t_idx = len(trade.targets) - 1
    final_t_name = f"T{final_t_idx + 1}"

    for i in range(trade.entry_idx + 1, end):
        bar_high = float(df[high_col].iloc[i])
        bar_low = float(df[low_col].iloc[i])

        if trade.direction == "long":
            # 1. Stop hit?
            if bar_low <= stop:
                trade.exit_idx = i
                trade.exit_price = stop
                trade.exit_reason = "trail_stop" if trail_active else "initial_stop"
                if trail_active and targets_hit:
                    trade.exit_reason += f" (targets {','.join(targets_hit)})"
                return trade
            # 2. Target markers (last target terminates the trade)
            for t_idx, t_price in enumerate(trade.targets):
                tname = f"T{t_idx + 1}"
                if bar_high >= t_price and tname not in targets_hit:
                    targets_hit.append(tname)
                    if t_idx == final_t_idx:
                        trade.exit_idx = i
                        trade.exit_price = t_price
                        trade.exit_reason = tname
                        return trade
            # 3. Trail activation — once price reaches the trail-activation price
            if not trail_active and bar_high >= trail_activation_price:
                trail_active = True
            # 4. Update trailing stop if active
            if trail_active:
                trail = three_bar_trailing_stop_long(df, trade.entry_idx, i, low_col, high_col)
                if trail > stop:
                    stop = trail

        else:  # short
            if bar_high >= stop:
                trade.exit_idx = i
                trade.exit_price = stop
                trade.exit_reason = "trail_stop" if trail_active else "initial_stop"
                if trail_active and targets_hit:
                    trade.exit_reason += f" (targets {','.join(targets_hit)})"
                return trade
            for t_idx, t_price in enumerate(trade.targets):
                tname = f"T{t_idx + 1}"
                if bar_low <= t_price and tname not in targets_hit:
                    targets_hit.append(tname)
                    if t_idx == final_t_idx:
                        trade.exit_idx = i
                        trade.exit_price = t_price
                        trade.exit_reason = tname
                        return trade
            if not trail_active and bar_low <= trail_activation_price:
                trail_active = True
            if trail_active:
                trail = three_bar_trailing_stop_short(df, trade.entry_idx, i, low_col, high_col)
                if trail < stop:
                    stop = trail

    # Time exit
    trade.exit_idx = end - 1
    trade.exit_price = float(df[close_col].iloc[end - 1])
    trade.exit_reason = f"time (targets {','.join(targets_hit) or 'none'})"
    return trade


def fib_long_at_p1(df: pd.DataFrame, rsi_col: str = "rsi14",
                    cfg: PatternConfig | None = None,
                    trail_activation_factor: float = TRAIL_ACTIVATION_FACTOR,
                    max_bars: int = 200) -> list[FibTrade]:
    cfg = cfg or PatternConfig()
    rsi = df[rsi_col].dropna()
    trades = []
    for p in detect_m(rsi, cfg):
        if p.completed_idx is None:
            continue
        entry_idx = p.anchors[0] + 1
        if entry_idx >= len(df):
            continue
        entry_price = float(df["close"].iloc[entry_idx])
        range_size, hi_idx, lo_idx = define_fib_range_long(df, p.anchors[0], p.completed_idx)
        if range_size <= 0:
            continue
        initial_stop = float(df["low"].iloc[lo_idx])
        targets = compute_fib_targets(entry_price, range_size, "long")
        t = FibTrade(direction="long", entry_idx=entry_idx, entry_price=entry_price,
                     range_size=range_size, range_high_idx=hi_idx, range_low_idx=lo_idx,
                     initial_stop=initial_stop, targets=targets)
        t = simulate_fib_trade(df, t, max_bars=max_bars,
                               trail_activation_factor=trail_activation_factor)
        trades.append(t)
    return trades


def define_fib_range_short_pre_t1(df: pd.DataFrame, t1_idx: int,
                                  high_col: str = "high",
                                  low_col: str = "low",
                                  lookback: int = 60) -> tuple[float, int, int]:
    """Symmetric mirror of ``define_fib_range_long`` for SHORT-at-T1+1 entries.

    Range = high(pre-T1 lookback window) − low(T1_bar). The 'high' is the
    most recent price ceiling BEFORE T1 (the prior M's top or local price
    ceiling), where T1 is the first trough of a strict-V.
    """
    n = len(df)
    if t1_idx <= 0:
        return 0.0, t1_idx, 0
    lb = min(t1_idx, lookback)
    seg = df.iloc[t1_idx - lb:t1_idx]
    high_pos = int(seg[high_col].values.argmax() + (t1_idx - lb))
    price_high = float(df[high_col].iloc[high_pos])
    price_low = float(df[low_col].iloc[t1_idx])
    range_size = price_high - price_low
    return range_size, high_pos, t1_idx


def fib_short_at_v_t1(df: pd.DataFrame, rsi_col: str = "rsi14",
                      v_cfg: Optional["StrictVConfig"] = None,  # type: ignore[name-defined]
                      trail_activation_factor: float = TRAIL_ACTIVATION_FACTOR,
                      max_bars: int = 200,
                      lookback_bars: int = 60) -> list[FibTrade]:
    """Symmetric SHORT mirror of ``fib_long_at_p1``.

    Entry at T1+1 of a strict-V pattern (first trough of V plus one bar).
    Range anchored from the pre-T1 60-bar lookback high down to T1's low.
    Initial stop = the lookback-window high price (above entry for shorts).
    Targets = T1 − 1.618×range, T1 − 2.236×range, T1 − 3.618×range.

    Uses ``patterns_strict_v.detect_strict_v`` which itself inverts the RSI
    series and reuses the strict-M detector. See ``patterns_strict_v.py``
    for the threshold-inversion math.
    """
    from .patterns_strict_v import detect_strict_v, StrictVConfig
    v_cfg = v_cfg or StrictVConfig()
    rsi = df[rsi_col].dropna()
    trades: list[FibTrade] = []
    for v in detect_strict_v(rsi, v_cfg):
        if v.completion_idx is None:
            continue
        # Map rsi-positional indices to df-positional via the rsi Series index.
        t1_rsi_pos = int(v.first_major_trough_idx)
        try:
            t1_ts = rsi.index[t1_rsi_pos]
            entry_ts = rsi.index[t1_rsi_pos + 1]
            t1_df = df.index.get_loc(t1_ts)
            entry_df = df.index.get_loc(entry_ts)
        except (IndexError, KeyError):
            continue
        if entry_df >= len(df):
            continue
        entry_price = float(df["close"].iloc[entry_df])
        range_size, hi_idx, lo_idx = define_fib_range_short_pre_t1(
            df, t1_df, lookback=lookback_bars,
        )
        if range_size <= 0:
            continue
        initial_stop = float(df["high"].iloc[hi_idx])
        if initial_stop <= entry_price:
            continue
        targets = compute_fib_targets(entry_price, range_size, "short")
        t = FibTrade(
            direction="short",
            entry_idx=entry_df,
            entry_price=entry_price,
            range_size=range_size,
            range_high_idx=hi_idx,
            range_low_idx=lo_idx,
            initial_stop=initial_stop,
            targets=targets,
        )
        t = simulate_fib_trade(df, t, max_bars=max_bars,
                               trail_activation_factor=trail_activation_factor)
        trades.append(t)
    return trades


def fib_short_at_v_floor(df: pd.DataFrame, rsi_col: str = "rsi14",
                          cfg: PatternConfig | None = None,
                          trail_activation_factor: float = TRAIL_ACTIVATION_FACTOR,
                          max_bars: int = 200) -> list[FibTrade]:
    from scipy.signal import find_peaks
    cfg = cfg or PatternConfig()
    rsi = df[rsi_col].dropna()
    rsi_arr = rsi.to_numpy()
    n = len(rsi_arr)
    trades = []
    for p in detect_v(rsi, cfg):
        if p.completed_idx is None:
            continue
        t1, t2 = p.anchors
        floor = float(min(rsi_arr[t1], rsi_arr[t2]))
        breach_idx = None
        for i in range(t2 + 1, min(t2 + 200, n)):
            if rsi_arr[i] < floor:
                breach_idx = i
                break
        if breach_idx is None or breach_idx + 1 >= len(df):
            continue
        entry_idx = breach_idx + 1
        entry_price = float(df["close"].iloc[entry_idx])
        range_size, hi_idx, lo_idx = define_fib_range_short(df, t2, breach_idx)
        if range_size <= 0:
            continue
        initial_stop = float(df["high"].iloc[hi_idx])
        targets = compute_fib_targets(entry_price, range_size, "short")
        t = FibTrade(direction="short", entry_idx=entry_idx, entry_price=entry_price,
                     range_size=range_size, range_high_idx=hi_idx, range_low_idx=lo_idx,
                     initial_stop=initial_stop, targets=targets)
        t = simulate_fib_trade(df, t, max_bars=max_bars,
                               trail_activation_factor=trail_activation_factor)
        trades.append(t)
    return trades


def trade_stats(trades: list[FibTrade], spread_bps: float = 2.0) -> dict:
    if not trades:
        return {"n": 0}
    rets = np.array([t.gross_return for t in trades if t.gross_return is not None])
    r_mults = np.array([t.r_multiple for t in trades if t.r_multiple is not None])
    spread = spread_bps / 10000.0
    net = rets - spread
    exit_reasons = pd.Series([t.exit_reason for t in trades]).value_counts()
    return {
        "n": len(trades),
        "gross_mean_return_pct": float(rets.mean() * 100),
        "net_mean_return_pct": float(net.mean() * 100),
        "median_return_pct": float(np.median(rets) * 100),
        "std_return_pct": float(rets.std() * 100),
        "win_rate": float((net > 0).mean()),
        "mean_R_multiple": float(r_mults.mean()) if len(r_mults) else None,
        "median_R_multiple": float(np.median(r_mults)) if len(r_mults) else None,
        "exit_reasons": exit_reasons.to_dict(),
        "best_trade_pct": float(rets.max() * 100),
        "worst_trade_pct": float(rets.min() * 100),
    }
