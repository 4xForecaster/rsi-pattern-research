"""Risk-adjusted performance metrics for trade lists.

Step 2 of the 5-step hardening plan. Converts per-trade R-multiples into
proper equity curves and computes Sharpe / Sortino / MAR / Calmar / max DD.

Conventions
-----------
- 1% of capital risked per trade by default; PnL per trade = R * risk * multiplier.
- Trades are realized on their exit date — no within-day MTM.
- Equity timeline is a daily calendar from the first entry to the last exit;
  equity steps up on exit days, flat in between.
- Annualization factor = sqrt(252) on daily returns (the equity curve is
  daily-indexed even when underlying data is daily DXY).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence
import math
import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class TradeRecord:
    """Minimal info needed to drive the equity curve."""
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    r_multiple: float
    multiplier: float = 1.0  # FLD scheme multiplier


@dataclass
class MTMTrade:
    """Trade with intra-trade bar-by-bar close prices for mark-to-market.

    Used for overlap-aware intraday equity curves where multiple positions
    can be open simultaneously.
    """
    entry_idx: int
    exit_idx: int
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    initial_stop: float
    exit_price: float
    direction: str = "long"
    multiplier: float = 1.0
    # spread (fractional, e.g. 0.0003 for 3 bps) charged on entry and exit price legs
    spread: float = 0.0
    # close series for the trade's life (entry..exit inclusive); index aligns with bar index
    closes: Optional[pd.Series] = None


def trades_from_fib(trades, df_index, multipliers: Optional[Sequence[float]] = None) -> list[TradeRecord]:
    """Convert FibTrade objects (with integer indices) to TradeRecord objects.

    `multipliers` is a per-trade list matching `trades` length; defaults to 1×.
    """
    if multipliers is None:
        multipliers = [1.0] * len(trades)
    out = []
    for t, m in zip(trades, multipliers):
        if t.exit_idx is None or t.r_multiple is None:
            continue
        if m == 0:
            continue
        out.append(TradeRecord(
            entry_date=pd.Timestamp(df_index[t.entry_idx]),
            exit_date=pd.Timestamp(df_index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(m),
        ))
    return out


def build_equity_curve(
    trades: Sequence[TradeRecord],
    initial_capital: float = 1.0,
    risk_per_trade: float = 0.01,
) -> pd.Series:
    """Construct a daily equity curve from a list of trades.

    PnL per trade is realized on its exit date: pnl = R * risk * mult * initial_capital.
    (Risk is on initial capital, i.e. fixed-fractional with no compounding of
    the risk amount — this keeps R-units interpretable across schemes.)
    """
    if not trades:
        idx = pd.date_range("2020-01-01", periods=1, freq="D")
        return pd.Series([initial_capital], index=idx, name="equity")

    first = min(t.entry_date for t in trades)
    last = max(t.exit_date for t in trades)
    idx = pd.date_range(first.normalize(), last.normalize(), freq="D")

    pnl_per_day = pd.Series(0.0, index=idx)
    for t in trades:
        d = t.exit_date.normalize()
        if d not in pnl_per_day.index:
            d = pnl_per_day.index[pnl_per_day.index.get_indexer([d], method="bfill")[0]]
        pnl_per_day.loc[d] += t.r_multiple * risk_per_trade * t.multiplier * initial_capital

    equity = initial_capital + pnl_per_day.cumsum()
    equity.name = "equity"
    return equity


def daily_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def build_equity_curve_mtm(
    trades: Sequence[MTMTrade],
    bar_close: pd.Series,
    initial_capital: float = 1.0,
    risk_per_trade: float = 0.01,
) -> pd.Series:
    """Overlap-aware mark-to-market equity curve for intraday strategies.

    At each bar t:
        equity[t] = initial_capital
                  + Σ realized PnL from trades closed by bar t
                  + Σ unrealized PnL from trades open at bar t (priced at close[t])

    Units for each trade are fixed at entry: mult * risk * cap /
    |entry - stop|. Spread is fractional (e.g. 0.0003 = 3 bps) and is
    charged on both legs in the direction that costs the trader:
        long  entry_eff = entry * (1 + spread)   (pays above close)
              exit_eff  = exit  * (1 - spread)   (sells below close)
              realized  = units * (exit_eff - entry_eff)
        short entry_eff = entry * (1 - spread)   (sells below close)
              exit_eff  = exit  * (1 + spread)   (covers above close)
              realized  = units * (entry_eff - exit_eff)
    """
    if not trades:
        return pd.Series([initial_capital], index=bar_close.index[:1], name="equity")

    n = len(bar_close)
    contrib = np.zeros(n, dtype=float)  # cumulative contribution from realized trades
    open_mtm = np.zeros(n, dtype=float)  # per-bar unrealized MTM (recomputed)
    idx_map = {ts: i for i, ts in enumerate(bar_close.index)}
    close_arr = bar_close.values

    for tr in trades:
        is_long = (tr.direction == "long")
        risk_per_unit = (tr.entry_price - tr.initial_stop) if is_long \
                        else (tr.initial_stop - tr.entry_price)
        if risk_per_unit <= 0:
            continue
        units = tr.multiplier * risk_per_trade * initial_capital / risk_per_unit
        if is_long:
            entry_eff = tr.entry_price * (1.0 + tr.spread)
            exit_eff  = tr.exit_price  * (1.0 - tr.spread)
            realized  = units * (exit_eff - entry_eff)
        else:
            entry_eff = tr.entry_price * (1.0 - tr.spread)
            exit_eff  = tr.exit_price  * (1.0 + tr.spread)
            realized  = units * (entry_eff - exit_eff)

        entry_pos = idx_map.get(tr.entry_date)
        exit_pos = idx_map.get(tr.exit_date)
        if entry_pos is None or exit_pos is None or exit_pos < entry_pos:
            continue

        # Unrealized MTM at every bar in [entry_pos, exit_pos)
        if exit_pos > entry_pos:
            slice_close = close_arr[entry_pos:exit_pos]
            if is_long:
                open_mtm[entry_pos:exit_pos] += units * (slice_close - entry_eff)
            else:
                open_mtm[entry_pos:exit_pos] += units * (entry_eff - slice_close)

        # Realized contribution from exit_pos onward
        contrib[exit_pos:] += realized

    equity = initial_capital + contrib + open_mtm
    return pd.Series(equity, index=bar_close.index, name="equity")


def sharpe(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    r = daily_returns(equity)
    if r.std(ddof=1) == 0 or len(r) < 2:
        return float("nan")
    return float(r.mean() / r.std(ddof=1) * math.sqrt(periods_per_year))


def sortino(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """Canonical Sortino: mean / downside_deviation, annualized.

    downside_deviation = sqrt(mean(min(0, r)^2)) taken over ALL periods
    (positive returns contribute 0, not excluded), which is the standard
    Sortino definition (Sortino & Price 1994).
    """
    r = daily_returns(equity)
    if len(r) < 2:
        return float("nan")
    neg = np.minimum(r.values, 0.0)
    dd = math.sqrt(float((neg ** 2).mean()))
    if dd == 0:
        return float("nan")
    return float(r.mean() / dd * math.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series) -> float:
    """Return max drawdown as a negative fraction (e.g. -0.13 == -13%)."""
    if len(equity) < 2:
        return 0.0
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return float("nan")
    start, end = equity.iloc[0], equity.iloc[-1]
    if start <= 0 or end <= 0:
        return float("nan")
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return float((end / start) ** (1.0 / years) - 1.0)


def mar(equity: pd.Series) -> float:
    """CAGR / |max DD| over the full sample."""
    mdd = max_drawdown(equity)
    if mdd == 0:
        return float("nan")
    return float(cagr(equity) / abs(mdd))


def calmar(equity: pd.Series, window_years: float = 3.0) -> float:
    """CAGR / |max DD| computed over the trailing window_years.

    Falls back to full-sample if the window is longer than available history.
    """
    if len(equity) < 2:
        return float("nan")
    cutoff = equity.index[-1] - pd.Timedelta(days=int(window_years * 365.25))
    tail = equity[equity.index >= cutoff]
    if len(tail) < 2 or tail.iloc[0] <= 0:
        tail = equity
    mdd = max_drawdown(tail)
    if mdd == 0:
        return float("nan")
    start, end = tail.iloc[0], tail.iloc[-1]
    years = (tail.index[-1] - tail.index[0]).days / 365.25
    if years <= 0 or start <= 0:
        return float("nan")
    tail_cagr = (end / start) ** (1.0 / years) - 1.0
    return float(tail_cagr / abs(mdd))


def total_r_per_year(trades: Sequence[TradeRecord]) -> float:
    if not trades:
        return float("nan")
    total_r = sum(t.r_multiple * t.multiplier for t in trades)
    first = min(t.entry_date for t in trades)
    last = max(t.exit_date for t in trades)
    years = (last - first).days / 365.25
    if years <= 0:
        return float("nan")
    return float(total_r / years)


def mean_r(trades: Sequence[TradeRecord]) -> float:
    if not trades:
        return float("nan")
    return float(np.mean([t.r_multiple * t.multiplier for t in trades]))


def summarize(name: str, trades: Sequence[TradeRecord], equity: pd.Series) -> dict:
    return {
        "scheme": name,
        "trades": len(trades),
        "mean_R": mean_r(trades),
        "total_R_per_year": total_r_per_year(trades),
        "sharpe": sharpe(equity),
        "sortino": sortino(equity),
        "calmar": calmar(equity),
        "mar": mar(equity),
        "max_dd": max_drawdown(equity),
    }
