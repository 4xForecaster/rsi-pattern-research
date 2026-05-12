# RSI M-P1 LONG — Operational Trading Spec

**Version 1.0 · 2026-05-12 · DXY daily**
Locked-in choices from hardening Steps 1–2 (H11, H12). Source-of-truth is
`src/rsi_pattern/{patterns,position_sizing,fld}.py`. Numeric params mirrored in
`results/spec_params.json` for programmatic ingest.

| # | Block | Rule |
|---|---|---|
| 1 | **Instrument · timeframe** | DXY, daily bars (BarChart Premier). Only timeframe and symbol validated in-sample/OOS. Cross-symbol untested — do not generalize without re-fitting thresholds. |
| 2 | **Pattern detector** | **Loose-M** on Wilder RSI(14). Two RSI peaks `P1, P2` (scipy `find_peaks`, prominence≥3.0, min distance 3 bars), both `≥65.0`. Span `P2−P1 ≤ 30 bars`. Dip between peaks `≥50.0`. **Completion**: RSI crosses below 50.0 within 30 bars after P2. |
| 3 | **Entry** | At **close of bar P1+1**, direction **LONG**. Pattern need not have completed by the entry bar — entry is anchored on P1, not on completion. |
| 4 | **Reference range** | `range = high(P1_bar) − low_in_60bar_lookback_before_P1`. The "low" is the minimum daily low in the 60-bar window immediately preceding P1 (rise-origin price floor). |
| 5 | **Initial stop** | `stop = low(60-bar_lookback_low_bar)`. Same bar that anchors the range's lower bound. **No ATR component** — purely structural. |
| 6 | **Position sizing** (Scheme D) | Read FLD bias at entry bar from cycles `(10, 20, 40)` (canonical Hurst, source `(H+L)/2`, shift `N//2+1`). Compare close to each FLD: bias `+1` if close > FLD, `−1` if close < FLD. Aggregate: **bullish** = all 3 `+1`; **bearish** = all 3 `−1`; **neutral** = mixed. Multipliers: **bullish → SKIP**, **neutral → 1×**, **bearish → 3×**. Base risk = 1% account equity. Units = `mult × 0.01 × equity / (entry_close − initial_stop)`. |
| 7 | **Targets** (SURF Fib) | `T1 = entry + 1.618 × range`, `T2 = entry + 2.236 × range`, `T3 = entry + 3.618 × range`. **T1 and T2 are markers only** — no stop adjustment when hit. |
| 8 | **Trail activation** | Once the bar's `high ≥ entry + 3.600 × range`, activate the 3-bar trailing stop. (Triggers near T3, before T3 itself.) |
| 9 | **Trail rule** | While active: `trail = min(low) over the last 3 higher-high bars since entry, excluding inside bars (bar where high<prev_high AND low>prev_low)`. Update each bar; stop ratchets only upward (never lowered). |
| 10 | **Exit (first of)** | (a) bar `low ≤ stop` → exit at stop price; (b) bar `high ≥ T3` → exit at T3 exactly; (c) 200 bars elapsed since entry → exit at close of bar 200 (time stop). |
| 11 | **Parallel positions** | Allowed. No de-duplication, no concurrency cap. Sized independently per signal; account-level risk is `Σ active_mult × 1%`. Historical peak concurrent exposure under Scheme D = 8×. |
| 12 | **Expected stats (Scheme D, 36-yr DXY in-sample + H9 OOS-validated)** | 56 trades · mean R **+4.15** · win rate 68% · total R/yr +6.78 · Sharpe +0.47 · **Sortino +5.75** · MAR +1.29 · Max DD **−2.78%** of equity. |

## Caveats (read before deploying capital)

- **Trailing-3y Calmar is negative for all schemes** (incl. unscaled A). The +30.7R 2022 USD melt-up was followed by 3 quiet/negative years. The edge survived H9 OOS validation but is in a cool regime — size new positions cautiously.
- **No cross-symbol validation.** Spec is DXY-only. Re-fit `m_peak_threshold`, `min_peak_prominence`, FLD cycles, and `max_bars` before applying to EUR/USD, gold, equities, etc.
- **FLD is the simplified canonical form** (median-price shift, no Sentient Trader confluence). Step 5 of the hardening plan swaps in the real hurst-agent FLD output. Until then, `fld.fld_bias` uses `(10, 20, 40)` fixed cycles.
- **Initial stop has no volatility floor.** For thin rise-origin lookbacks the stop can sit very close to entry — risk per unit is small but slippage cost on a stop-out is proportionally larger. Acceptable per H12 results; monitor.

## Discrepancies between this spec and the user's Step-3 draft

Resolved by treating the **code as ground truth** (H11/H12 backtests called `fib_long_at_p1` which calls `detect_m`, not `detect_strict_m`). Three items differ from the draft prompt:

1. **Detector is loose-M, not strict-M.** The draft cited strict-M thresholds (origin <30, peaks ≥75.01, wiggle ≥70). Those define `patterns_strict.detect_strict_m` and produce ~5 trades on DXY daily. The 124-trade backtest used the loose definition above (peaks ≥65, dip ≥50, completes <50). Switching to strict-M would invalidate the H11/H12 results.
2. **Initial stop has no ATR term.** Draft said `min(structural_low, entry − 1×ATR14)`. Code uses the 60-bar lookback low only. ATR(14) is never computed in this strategy.
3. **Range anchor is pre-P1, not post-P1.** Draft said "RSI-pattern high and subsequent low prior to entry." Code anchors the range low at the 60-bar window *before* P1 (the rise-origin floor), not anywhere between P1 and the entry bar.

If any of (1)–(3) reflect Dr. A's true intent, treat this spec as describing the *current* code and re-run H11/H12 against a corrected `fib_long_at_p1` before adopting changes.
