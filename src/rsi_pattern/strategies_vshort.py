"""V-pattern SHORT — first-class symmetric counterpart to the M-P1 LONG stack.

The M-P1 LONG pipeline (``position_sizing.fib_long_at_p1`` +
FLD-bias Scheme D + ``risk_metrics``) trades RSI M-tops long. This module
is its mirror: it trades RSI **V-floor breakdowns short**, reusing the
already-H8-tested short engine in ``position_sizing`` so the implementation
is faithful by construction (no re-derivation of the short mechanics).

Faithfulness anchor (H8, results/H8_surf_fib_backtest.md): DXY daily
V-floor SHORT through ``fib_short_at_v_floor`` + ``trade_stats`` →
mean R-multiple **+0.48**. ``vshort_records`` below feeds the *same*
``FibTrade`` objects into the same ``risk_metrics`` harness the LONG side
uses, so a DXY replay reproduces +0.48 and the cross-symbol numbers are
directly comparable to the M-LONG H23/H24 figures.

Design rules (locked, H25 brief):
  * Detector: ``patterns.detect_v`` (RSI-14 V), same default ``PatternConfig``
    used by the LONG side's M detector — **no per-pair tuning**.
  * Entry: SHORT at close of the bar after RSI breaks below the lower of
    the two V troughs (the H8 "V-floor breach"). Implemented in
    ``position_sizing.fib_short_at_v_floor`` — reused verbatim.
  * Range: V-high − V-floor (mirror of the M range).
  * Targets: SURF Fib 1.618 / 2.236 / 3.618 × range *below* entry.
  * Trail: 3-bar trailing stop arms at 3.600× range; high of the last 3
    lower-low bars excluding inside bars — the inverse of the long rule
    (``position_sizing.three_bar_trailing_stop_short``).
  * Sizing: same Scheme D *structure*, FLD bias read at the SHORT entry
    bar. Per the brief: bullish FLD = wrong direction → skip (0×),
    neutral → 1×, bearish (favorable for a short) → 3×. NOTE: this maps
    to the tuple ``(bullish=0, neutral=1, bearish=3)`` which is
    *numerically identical* to the M-LONG Scheme D tuple — that
    coincidence is expected, not a bug: in both cases the favorable-
    confirmation bucket gets 3× and the contrary bucket is skipped.

Pure functions, explicit config, no module globals beyond the immutable
default Scheme D tuple.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import indicators, fld
from . import position_sizing as ps
from . import risk_metrics as rm
from .patterns import PatternConfig

# (bullish, neutral, bearish) — see module docstring for why this equals
# the M-LONG tuple. Immutable; callers may pass an override.
SCHEME_D_VSHORT: tuple[float, float, float] = (0.0, 1.0, 3.0)


@dataclass(frozen=True)
class VShortResult:
    """Metrics for one V-SHORT backtest slice."""

    label: str
    trades: int
    universe: int
    bias_counts: dict
    mean_R_weighted: float
    total_R_per_year: float
    sharpe: float
    sortino: float
    calmar: float
    mar: float
    max_dd: float
    equity: pd.Series
    records: list


def vshort_records(
    df: pd.DataFrame,
    *,
    cycles: tuple[int, ...] = (10, 20, 40),
    scheme_d: tuple[float, float, float] = SCHEME_D_VSHORT,
    rsi_period: int = 14,
    pattern_cfg: Optional[PatternConfig] = None,
) -> tuple[list[rm.TradeRecord], dict, int]:
    """Generate Scheme-D-weighted V-SHORT TradeRecords for ``df``.

    Mirror of H23's ``run_one`` record-construction, SHORT side. Returns
    ``(records, bias_counts, universe)``. ``df`` must have OHLC columns;
    RSI is added internally. FLD bias is read at the SHORT entry bar.
    """
    pattern_cfg = pattern_cfg or PatternConfig()
    df_rsi = indicators.add_rsi(df, period=rsi_period)
    rsi_col = f"rsi{rsi_period}"
    trades = ps.fib_short_at_v_floor(df_rsi, rsi_col=rsi_col, cfg=pattern_cfg)
    bias = fld.fld_bias(df_rsi, cycles=cycles)

    bull_m, neut_m, bear_m = scheme_d
    records: list[rm.TradeRecord] = []
    bias_counts = {"bullish": 0, "neutral": 0, "bearish": 0, "unknown": 0}
    universe = 0
    for t in trades:
        if t.exit_idx is None or t.r_multiple is None:
            continue
        universe += 1
        entry_ts = df_rsi.index[t.entry_idx]
        lbl = (bias.loc[entry_ts, "bias_label"]
               if entry_ts in bias.index else "unknown")
        bias_counts[lbl] = bias_counts.get(lbl, 0) + 1
        # SHORT: bullish FLD = wrong direction (skip); bearish = favorable (3×)
        if lbl == "bullish":
            mult = bull_m
        elif lbl == "bearish":
            mult = bear_m
        else:
            mult = neut_m
        if mult == 0:
            continue
        records.append(rm.TradeRecord(
            entry_date=pd.Timestamp(entry_ts),
            exit_date=pd.Timestamp(df_rsi.index[t.exit_idx]),
            r_multiple=float(t.r_multiple),
            multiplier=float(mult),
        ))
    return records, bias_counts, universe


def run_vshort(
    df: pd.DataFrame,
    *,
    label: str,
    cycles: tuple[int, ...] = (10, 20, 40),
    scheme_d: tuple[float, float, float] = SCHEME_D_VSHORT,
) -> VShortResult:
    """End-to-end V-SHORT backtest on ``df`` → metrics via the shared
    ``risk_metrics`` harness (identical path to the M-LONG side, so
    Sortino is directly comparable to H23/H24)."""
    import numpy as np

    records, bias_counts, universe = vshort_records(
        df, cycles=cycles, scheme_d=scheme_d)
    equity = rm.build_equity_curve(records, initial_capital=1.0,
                                   risk_per_trade=0.01)
    return VShortResult(
        label=label,
        trades=len(records),
        universe=universe,
        bias_counts=bias_counts,
        mean_R_weighted=(float(np.mean([r.r_multiple * r.multiplier
                                        for r in records]))
                         if records else float("nan")),
        total_R_per_year=rm.total_r_per_year(records),
        sharpe=rm.sharpe(equity),
        sortino=rm.sortino(equity),
        calmar=rm.calmar(equity),
        mar=rm.mar(equity),
        max_dd=rm.max_drawdown(equity),
        equity=equity,
        records=records,
    )


def faithfulness_mean_r(df: pd.DataFrame, *, spread_bps: float = 2.0) -> float:
    """H8 replay metric: unweighted mean R-multiple of the raw V-floor
    SHORT FibTrades on ``df`` (no Scheme D). H8 anchor on DXY daily = +0.48.
    """
    df_rsi = indicators.add_rsi(df, period=14)
    trades = ps.fib_short_at_v_floor(df_rsi, rsi_col="rsi14")
    stats = ps.trade_stats(trades, spread_bps=spread_bps)
    return float(stats.get("mean_R_multiple", float("nan")))


# --- symmetry-test surface ------------------------------------------------
# Thin re-exports so the unit test can assert the long-side and short-side
# 3-bar trailing-stop + inside-bar logic are exact mirror images without
# reaching into position_sizing internals.

def trailing_stop_long(df: pd.DataFrame, start_idx: int, current_idx: int,
                        low_col: str = "low", high_col: str = "high") -> float:
    return ps.three_bar_trailing_stop_long(df, start_idx, current_idx,
                                           low_col, high_col)


def trailing_stop_short(df: pd.DataFrame, start_idx: int, current_idx: int,
                        low_col: str = "low", high_col: str = "high") -> float:
    return ps.three_bar_trailing_stop_short(df, start_idx, current_idx,
                                            low_col, high_col)
