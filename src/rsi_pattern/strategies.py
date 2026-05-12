"""Codified trading strategies derived from RSI M/V findings.

Each strategy is a deterministic mapping from market state to entry/exit
events. Backtest harness applies entries at the close of the signal bar +1
(realistic execution lag), exits at the close of the K-th forward bar or at
a structural exit (e.g., M-bottom-breach for long-M strategies).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import numpy as np
import pandas as pd

from .patterns import detect_m, detect_v, detect_all, PatternConfig


@dataclass
class TradeRecord:
    direction: Literal["long", "short"]
    entry_idx: int
    exit_idx: int
    entry_price: float
    exit_price: float
    bars_held: int

    @property
    def gross_return(self) -> float:
        if self.direction == "long":
            return np.log(self.exit_price) - np.log(self.entry_price)
        return np.log(self.entry_price) - np.log(self.exit_price)


def long_at_p1(df: pd.DataFrame, hold_bars: int = 20,
               rsi_col: str = "rsi14", close_col: str = "close",
               cfg: PatternConfig | None = None) -> list[TradeRecord]:
    """LONG entry at P1+1 (next bar after first peak of M is identified).
    Exit at entry+hold_bars close.

    Flipped version of the originally-proposed "short at M-top" intuition.
    Per Run 4 results, P1 entry on daily 20d hold has d=+1.44.
    """
    cfg = cfg or PatternConfig()
    rsi = df[rsi_col].dropna()
    n = len(df)
    trades = []
    for p in detect_m(rsi, cfg):
        if p.completed_idx is None:
            continue
        entry_idx = p.anchors[0] + 1   # P1+1, realistic execution lag
        exit_idx = min(entry_idx + hold_bars, n - 1)
        if entry_idx >= n or exit_idx <= entry_idx:
            continue
        trades.append(TradeRecord(
            direction="long",
            entry_idx=entry_idx, exit_idx=exit_idx,
            entry_price=float(df[close_col].iloc[entry_idx]),
            exit_price=float(df[close_col].iloc[exit_idx]),
            bars_held=exit_idx - entry_idx,
        ))
    return trades


def short_at_v_floor_breach(df: pd.DataFrame, hold_bars: int = 20,
                             rsi_col: str = "rsi14", close_col: str = "close",
                             cfg: PatternConfig | None = None) -> list[TradeRecord]:
    """SHORT entry at the bar where RSI breaks below V's floor (min of T1/T2 levels).
    Exit at entry+hold_bars close. Daily 20d Cohen's d = -1.53 unconditionally.
    """
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
        for i in range(t2 + 1, min(t2 + 200, n)):
            if rsi_arr[i] < floor:
                entry_idx = i + 1  # next bar after breach
                exit_idx = min(entry_idx + hold_bars, n - 1)
                if entry_idx >= n or exit_idx <= entry_idx:
                    break
                trades.append(TradeRecord(
                    direction="short",
                    entry_idx=entry_idx, exit_idx=exit_idx,
                    entry_price=float(df[close_col].iloc[entry_idx]),
                    exit_price=float(df[close_col].iloc[exit_idx]),
                    bars_held=exit_idx - entry_idx,
                ))
                break
    return trades


def summarize(trades: list[TradeRecord], spread_bps: float = 0.0) -> dict:
    """Compute trade statistics. spread_bps = round-trip cost in basis points."""
    if not trades:
        return {"n": 0}
    rets = np.array([t.gross_return for t in trades])
    spread_cost = spread_bps / 10000.0
    net_rets = rets - spread_cost
    return {
        "n": len(trades),
        "gross_mean_return_pct": float(rets.mean() * 100),
        "net_mean_return_pct": float(net_rets.mean() * 100),
        "std_return_pct": float(rets.std() * 100),
        "win_rate": float((net_rets > 0).mean()),
        "sum_log_return": float(net_rets.sum()),
        "cumulative_pct": float((np.exp(net_rets.sum()) - 1) * 100),
        "best_trade_pct": float(rets.max() * 100),
        "worst_trade_pct": float(rets.min() * 100),
    }
