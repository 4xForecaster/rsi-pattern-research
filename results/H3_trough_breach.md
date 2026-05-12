# H3 Extension — Trough-breach signals + M lifecycle stats (Run 3)

**Date:** 2026-05-12
**Source idea:** User proposed using RSI breaks below structural support levels (M-dip, M-bottom, V-floor) as short signals, plus using M duration/amplitude statistics to time entries.

## M lifecycle statistics

Striking finding: **M duration and amplitude are nearly identical across timeframes.** This is fractal self-similarity in another form.

| Timeframe | n patterns | Duration mean (bars) | Median | Std | Amplitude mean (RSI units) |
|---|---|---|---|---|---|
| Daily | 124 | 20.1 | 18 | 7.8 | 12.1 |
| 4h | 36 | 18.1 | 18 | 8.1 | 11.7 |
| 1h | 253 | 21.3 | 20 | 9.0 | 12.6 |
| 5m | 255 | 20.5 | 20 | 7.9 | 12.0 |

V patterns show similar statistics (mirror).

**Practical implication:** Once an M reaches ~18-22 bars from P1, the breakdown is statistically imminent regardless of timeframe.

## Forward returns at four candidate entry points

Tested every reasonable short-entry along the M lifecycle. **All early entries predict POSITIVE forward returns** (i.e., the M acts as a continuation-UP pattern on DXY). Only the late M-bottom breach shows weak short signal.

### Daily (n=124 M patterns)

| Entry | 1d | 5d | 20d | 60d |
|---|---|---|---|---|
| P1 (first peak) | +0.09% (d=+0.19) * | +0.59% (d=+0.55) *** | **+2.79% (d=+1.44) *** ** | +2.92% (d=+0.80) *** |
| P2 (second peak) | +0.17% (d=+0.35) *** | +0.86% (d=+0.83) *** | +1.90% (d=+0.97) *** | +2.16% (d=+0.57) *** |
| Dip-breach down | +0.17% (d=+0.35) *** | +0.86% (d=+0.82) *** | +1.15% (d=+0.58) *** | +1.47% (d=+0.37) *** |
| M-bottom breach | +0.12% (d=+0.24) ** | +0.29% (d=+0.25) ** | **-0.36% (d=-0.18)** * | +0.05% (ns) |

### 1h (n=253 M patterns)

| Entry | 1h | 5h | 20h | 60h |
|---|---|---|---|---|
| P1 | +0.02% (d=+0.20) *** | +0.07% (d=+0.42) *** | **+0.40% (d=+1.28) *** ** | +0.32% (d=+0.60) *** |
| P2 | +0.02% (d=+0.29) *** | +0.11% (d=+0.59) *** | +0.27% (d=+0.83) *** | +0.19% (d=+0.36) *** |
| Dip-breach | +0.03% (d=+0.33) *** | +0.11% (d=+0.64) *** | +0.14% (d=+0.43) *** | +0.08% (d=+0.17) ** |
| M-bottom breach | +0.01% (d=+0.17) ** | +0.02% (d=+0.15) ** | **-0.13% (d=-0.39)** *** | **-0.17% (d=-0.27)** *** |

Same pattern on 4h and 5m: P1, P2, Dip-breach all bullish; M-bottom breach weakly bearish at 20+ bars.

## V-floor breach (separate test)

| Timeframe | Horizon | n | Mean return | Cohen's d |
|---|---|---|---|---|
| Daily | 20d | 63 | **-2.93%** | **-1.53 *** ** |
| Daily | 60d | 63 | -2.56% | -0.73 *** |
| 4h | 20×4h | 27 | -1.07% | -1.53 *** |
| 1h | 20h | 136 | -0.55% | **-1.44 *** ** |
| 5m | 20×5m | 121 | -0.15% | -1.31 *** |

**V-floor breach is the strongest single short signal in the entire study.** Across timeframes, Cohen's d ranges -1.3 to -1.5 at the 20-bar horizon — institutional-grade effect size.

## Interpretation

The M pattern in DXY RSI is **empirically a continuation-up pattern**, not a topping reversal. Entering long at any point during M formation produces strong positive forward returns out to 20-60 bars. The biggest single edge is **P1 + 20d hold on daily: +2.79% mean return, Cohen's d = +1.44**.

The V pattern is symmetric on the short side. When V's floor fails (the bottom doesn't hold), price continues lower with massive effect size (d = -1.5).

Asymmetric reading:
- M = bullish continuation. Trade as a long setup.
- V = bottoming pattern. When V succeeds, price rallies (modest edge). When V fails (floor breaks), strong continuation down.

This is opposite to the naive "RSI overbought = sell, RSI oversold = buy" intuition. The market doesn't mean-revert at these RSI patterns; it continues.

## Practical signal summary

Strongest entries by direction:

**Short signals:**
- V-floor breach: d = -1.5 on daily 20-bar (PRIMARY)
- C→M transition: d = -0.97 on 1h 1-bar (FAST, 1-bar hold only)
- M-bottom breach: d = -0.39 on 1h 20-bar (WEAK, optional confirmation)

**Long signals:**
- P1 entry into M: d = +1.44 on daily 20-bar (STRONGEST IN STUDY)
- P2 entry: d = +0.97 on daily 20-bar
- Dip-breach during M's right leg: d = +0.58 on daily 20-bar
- C→V transition: d = +0.84 on 1h 1-bar (FAST)

## Code

New first-class functions in `src/rsi_pattern/validate.py`:

```python
m_lifecycle_stats(df, rsi_col="rsi14") -> dict           # duration + amplitude per M
v_lifecycle_stats(df, rsi_col="rsi14") -> dict           # mirror for V
trough_breach_signals(df, rsi_col="rsi14") -> dict       # m_dip, m_bottom, v_floor signals
```

Usage:
```python
from rsi_pattern import data, indicators, patterns, validate

df = patterns.detect_all(indicators.add_rsi(data.load_dxy("daily")))
stats = validate.m_lifecycle_stats(df)
print(f"Mean M duration: {stats['duration_bars']['mean']:.1f} bars")

signals = validate.trough_breach_signals(df)
print(f"V-floor breach signals: {len(signals['v_floor_breach'])}")
```

## Open questions / next tests

1. **Regime conditioning.** Does M predict UP only in bull-DXY regimes (where unconditional drift is positive)? Slice by 200-day MA direction or by Hurst FLD bias.
2. **Replication on EURUSD, USDCHF, USDMXN.** User's screenshots showed the same M/C/V topology on USDCHF and USDMXN. Does the up-direction edge survive on cross-rates?
3. **Trading costs.** Net edge after DXY spread (typically 1-2 pips on retail FX) on 5m and 1h. Daily and 4h edges are large enough to dominate costs; intraday may not be.
4. **Real-time detection latency.** P1 detection requires the next bar to confirm a local max. Live trader can act at P1+1 close at earliest. How much edge survives that 1-bar lag?
