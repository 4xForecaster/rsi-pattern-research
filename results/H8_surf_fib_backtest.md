# H8 — SURF Fibonacci Position Management Backtest

**Date:** 2026-05-12

Per Dr. A's specification:
- Reference RANGE = price excursion between RSI pattern's high and subsequent low
- Targets at **1.618x, 2.236x, and 3.618x** that range, projected in trade direction
- **3-bar trailing stop** (low of last 3 higher-high bars, excluding inside bars) activates after first target hits

This replaces the "fixed 20-bar hold" with realistic stop-and-target management.

## Daily DXY results

### LONG @ P1 of M

| Metric | Value |
|---|---|
| Trades | 124 |
| Net mean return / trade | **+2.45%** |
| Median return / trade | **+3.15%** |
| Std deviation | 4.60% |
| Win rate | 76% |
| **Mean R-multiple** | **+1.13** |
| Median R-multiple | +1.15 |
| Best / worst single trade | +10.94% / -10.90% |

**Exit reason breakdown:**

| Exit type | Count | Implication |
|---|---|---|
| trail_after_T1 | 41 | Hit T1, trailed up, exited on trail |
| time (no targets) | 34 | Held 200 bars, no target hit, exit at close |
| stop (initial) | 21 | Loss — hit initial stop before T1 |
| trail_after_T2 | 19 | Hit T1+T2, trailed up to T3 region, exited on trail |
| T3 | 7 | Hit T3 cleanly — best outcome |
| time (T1 hit) | 2 | T1 hit but rest never came |

**Read:** The strategy reaches at least T1 on **54% of trades** (67 of 124). T3 cleanly hits 7 times. The 21 stop-outs are 17% of trades, mean -7% per stop. This is REAL stop risk, not the 99% win rate the fixed-hold version implied.

### SHORT @ V-floor breach

| Metric | Value |
|---|---|
| Trades | 63 |
| Net mean return / trade | +1.47% |
| Median return / trade | +0.87% |
| Std deviation | 5.03% |
| Win rate | 56% |
| Mean R-multiple | **+0.48** |
| Median R-multiple | +0.10 |
| Best / worst single trade | +13.66% / -8.08% |

**Exit reason breakdown:**

| Exit type | Count |
|---|---|
| time (no targets) | 25 |
| stop (initial) | 24 |
| trail_after_T1 | 13 |
| trail_after_T2 | 1 |

**Read:** Only **22% of short trades** reach T1. **38% get stopped out** before any target. Median R-multiple = 0.10 — half of trades barely make any money. The unconditional Cohen's d=-1.53 captured the static 20-bar mean drift, but realistic stop-loss management catches many false-breakdown shakeouts.

## 1h DXY results

### LONG @ P1

| Metric | Value |
|---|---|
| Trades | 253 |
| Net mean return / trade | +0.22% |
| Median return | +0.31% |
| Win rate | 63% |
| Mean R-multiple | +0.67 |
| Median R-multiple | +0.71 |
| Best / worst trade | +1.84% / -1.79% |

### SHORT @ V-floor

| Metric | Value |
|---|---|
| Trades | 136 |
| Net mean return / trade | +0.34% |
| Median return | +0.25% |
| Win rate | 57% |
| Mean R-multiple | +0.79 |
| Median R-multiple | +0.37 |

## Conclusion

**LONG @ P1 with SURF Fib management is the cleanest tradeable system in this project so far.**

- 124 daily trades over 36 years
- 76% win rate (not 99% — that was the fixed-hold illusion)
- 1.13R mean per trade
- Asymmetric payoff: T3 hits 7 times for +10%+ each, stop-outs are -7% average

**SHORT @ V-floor degrades under realistic management.**

The 22% T1-hit rate suggests V-floor breach is **not** a clean continuation signal once realistic stops are applied. The signal works in aggregate (positive mean) but the median trade is essentially break-even. False breakdowns (where price quickly reverses back through the V's floor) eat the edge.

This is a critical finding: **the unconditional Cohen's d=-1.53 was misleading.** It captured a 20-bar static forward return mean, which a real trader cannot capture without enduring large unrealized drawdowns. Under stop discipline, half of those trades get stopped before the move materializes.

## Key trade math

For the LONG @ P1 daily strategy with 1% capital risked per trade:
- 124 trades over 36 years ≈ 3.4 trades/year
- 1.13R mean = 1.13% capital gain per trade × 3.4 trades = +3.8% annual
- 76% win rate, median 1.15R per win, average -7% per stop
- Sharpe-like ratio (mean / std) = 2.45 / 4.60 ≈ 0.53 per trade

Not an annualized blockbuster, but a real edge that's:
- **Statistically robust** across 36 years of data
- **Mechanically defined** with no discretion
- **Cleanly stoppable** with the 3-bar trailing rule

## Caveats / open

1. **Range definition for short trades** uses a 60-bar lookback for V's price-height. May be too wide for shorter timeframes. Sensitivity test recommended.
2. **Trailing stop activates after T1.** Tried a variant activating only after T2 — slightly different stats. The optimal activation rule depends on Dr. A's preferred risk tolerance.
3. **Inside-bar exclusion** in the trailing stop follows standard convention. Edge cases (multiple consecutive inside bars) may need refinement.
4. **No position sizing logic** yet — every trade is the same size. Real implementation should scale position to constant R risk per trade.

## Code

- `src/rsi_pattern/position_sizing.py` — FibTrade, simulate_fib_trade, fib_long_at_p1, fib_short_at_v_floor
- `compute_fib_targets(entry_price, range_size, direction)` — returns T1/T2/T3
- `three_bar_trailing_stop_long/short(df, start_idx, current_idx)` — trailing-stop function with inside-bar exclusion

## Next

- Real position sizing: scale to constant 1% capital risk per trade based on (entry - initial_stop) distance
- Sensitivity test on trailing activation rule (after T1 vs after T2 vs at entry)
- Same backtest with FLD bias filter (combine H7's null-result FLD with this)
- Cross-symbol test once hardened
