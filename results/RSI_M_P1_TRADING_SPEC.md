# RSI M-P1 LONG — Operational Trading Spec

**Version 1.1 · 2026-05-12 · DXY daily**
Locked-in choices from hardening Steps 1–3 (H11, H12, H13). v1.1 records the
empirical resolution of the three spec discrepancies via the H13 ablation
([`H13_ablation_for_spec.md`](H13_ablation_for_spec.md)) — all three knobs
held at their current-code values because each won on Sortino. **No rule
changes from v1.0; only the rationale is upgraded from "what the code does"
to "what the code does, verified to be the empirical optimum."**

Source-of-truth is `src/rsi_pattern/{patterns,position_sizing,fld}.py`.
Numeric params mirrored in `results/spec_params.json` for programmatic ingest.

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

## H13 ablation — discrepancies resolved empirically

Under Scheme D rules with everything else held constant (skip bullish FLD, 1× neutral, 3× bearish; SURF Fib; trail at 3.600×; 200-bar time stop; 1990–2026 daily DXY). Full details in [`H13_ablation_for_spec.md`](H13_ablation_for_spec.md). Selection rule: highest Sortino, ≥20 trades required.

| Cell | Trades | Mean R | Sortino | Max DD | Verdict |
|---|---|---|---|---|---|
| **baseline (loose / struct / pre-P1)** | 56 | +4.15 | **+5.75** | -2.78% | **WINS** |
| v1 strict-M | 2 | +2.03 | +0.74 | -0.95% | excluded (<20 trades) |
| v2 wider stop (ATR floor) | 56 | +3.53 | +4.77 | -3.08% | loses on Sortino (−17%) |
| v3 pre-entry range | 56 | +7.29 | +3.79 | -6.45% | loses on Sortino; flagged for possible Scheme F |
| v_all | 2 | +7.59 | n/a | 0.00% | excluded (<20 trades) |

1. **Detector — loose-M wins.** Strict-M generates only 2 trades on daily DXY (its thresholds are calibrated for higher-frequency oscillations). Empirically not better; not even testable on this timeframe.
2. **Initial stop — structural-only wins.** Adding an ATR floor cost +0.98 Sortino and +0.62 Mean R while leaving Max DD slightly worse. The structural stops aren't being whipsawed enough to need padding.
3. **Range — pre-P1 wins on Sortino.** Pre-entry range produces higher Mean R (+7.29) and +9.41 Calmar but loses on Sortino (+3.79) and triples Max DD to −6.45%. Worth revisiting under a return-maxing variant (Scheme F) in a future step.
