# RSI M-P1 Intraday Execution — Operational Trading Spec

**Version 1.0 · 2026-05-12 · DXY 5m (primary), 15m (secondary)**
Top-of-stack execution layer for the M-P1 strategy. Daily Scheme D
([`RSI_M_P1_TRADING_SPEC.md`](RSI_M_P1_TRADING_SPEC.md) v1.1) demotes to
regime/confluence overlay. Calibration source: H14 Phases 1–2
([`H14_intraday_execution.md`](H14_intraday_execution.md)). Programmatic
params: [`h14_intraday_spec_params.json`](h14_intraday_spec_params.json).
Source-of-truth code: [`src/rsi_pattern/intraday.py`](../src/rsi_pattern/intraday.py).

## Primary spec — 5m DXY · Scheme C

| # | Block | Rule (5m) |
|---|---|---|
| 1 | **Instrument · timeframe** | DXY, 5-minute bars (BarChart Premier). 15m allowed as secondary; see secondary spec below. Other symbols / TFs **not validated**. |
| 2 | **Detector** | **Strict-M** (`patterns_strict.detect_strict_m`) with H14-calibrated thresholds: `rise_origin_below=30`, `major_peak_min=72`, `wiggle_trough_floor=72`, `completion_threshold=50`, `max_rise_bars=60`, `max_top_zone_bars=60`, `max_completion_bars=60`. **`first_major_peak_idx` is the P1 anchor.** |
| 3 | **Entry** | Close of bar **P1+1**, **LONG**. Pattern need not have visibly completed by entry — entry anchors on P1, completion is a filter the detector applies retrospectively. |
| 4 | **Reference range** | `range = high(P1_bar) − min(low) over [P1−160, P1)`. **Lookback = 160 bars = 1× longest FLD cycle.** |
| 5 | **Initial stop** | `stop = low(bar_of_pre-P1_160bar_floor)`. Structural-only. (Wider-ATR floor tested in H14 ablation; rejected — ATR(14) on 5m always sits inside the structural distance, so the wider-of rule is a no-op.) |
| 6 | **FLD bias** | Cycles **(40, 80, 160)** bars, source `(H+L)/2`, shift `N//2+1`. Bullish = all 3 cycles below close; bearish = all 3 above; neutral = mixed. |
| 7 | **Position sizing — Scheme C** | Multipliers by FLD bias at entry: **bullish = 1×**, **neutral = 1×**, **bearish = 5×**. Base risk = 1% account equity. Units = `mult × 0.01 × equity / (entry_close − initial_stop)`. (Daily uses D; 5m winner is C — different bias counts at intraday make bullish entries net-positive.) |
| 8 | **Targets (SURF Fib)** | T1 = entry + 1.618 × range, T2 = +2.236, T3 = +3.618. T1/T2 are markers only. |
| 9 | **Trail activation** | Once `bar high ≥ entry + 3.600 × range`. |
| 10 | **Trail rule** | `min(low)` over last 3 higher-high bars since entry, excluding inside bars (high < prev_high AND low > prev_low). Monotonic upward. |
| 11 | **Exit (first of)** | (a) `bar low ≤ stop` → exit at stop; (b) `bar high ≥ T3` → exit at T3; (c) **160 bars** since entry → exit at close of bar 160. |
| 12 | **Spread** | **3 bps** charged on entry (long pays a touch above close) and exit (long sells a touch below close). |
| 13 | **Parallel positions** | Allowed. **Overlap-aware MTM is mandatory** — multiple positions are routine at 5m. No concurrency cap. Implementation: `risk_metrics.build_equity_curve_mtm`. Historical peak concurrent exposure under Scheme C ≈ 14× (driven by 5× bearish bursts). |
| 14 | **Daily regime overlay** *(provisional — not yet enforced in code)* | Recommended: only take a 5m entry when daily FLD bias ≠ "bullish (all 3)" — i.e., the daily Scheme D filter agrees that we're not in a fully bullish daily regime. Pending Step 4 implementation. |
| 15 | **Expected stats (5m, 2026-01-21 → 2026-05-04, 104 days)** | 69 trades · Mean R (weighted) **+1.77** · Total R/yr **+442** (annualized off 3.5 months — extrapolation) · Sharpe **+4.03** · Sortino **+6.19** · Calmar **+59.6** · MAR **+47.5** · Max DD **−13.51%**. |

## Secondary spec — 15m DXY (caveated)

15m on the same 104-day window produces only 18 strict-M trades on the
baseline config — **below the 20-trade validity floor**. Two ways to use 15m:

1. **Baseline 15m (informational)** — same rules as 5m above, with these
   changes: FLD cycles **(32, 64, 128)**, range lookback **64 bars** (= 0.5×
   longest cycle, identical metrics to 1× for this sample), time stop **128
   bars**, spread **2.5 bps**. 18 trades, Sortino +3.28, Max DD −15.2%. Use
   for slow-tape conditions or as a confluence check, not for primary signal
   generation.
2. **15m hypothesis (loose+pre-entry, 84 trades)** — switches detector to
   loose-M, range to pre-entry (M's inner trough), and stop to wider-of
   structural/ATR(14). Scored Sortino **+13.76** on this window but with
   completely different knob settings than 5m. **Do not deploy without
   out-of-sample re-test on a longer 15m archive.**

## Differences from daily Scheme D spec (v1.1)

| Dimension | Daily ([v1.1](RSI_M_P1_TRADING_SPEC.md)) | 5m intraday (this spec) |
|---|---|---|
| Detector | Loose-M (peaks ≥65, dip ≥50) | Strict-M (origin <30, peaks ≥72, wiggle ≥72) |
| Winning scheme | **D** (skip bullish) | **C** (5× bearish, keep all) |
| FLD cycles | (10, 20, 40) | (40, 80, 160) |
| Range lookback | 60 bars (≈ 2.7 months) | 160 bars (≈ 13.3 hours) |
| Time stop | 200 bars (≈ 9 months) | 160 bars (≈ 13.3 hours) |
| Spread | 2 bps | 3 bps |
| Equity curve | Realized-on-exit (no MTM) | Overlap-aware bar-by-bar MTM |
| Use case | Regime/bias filter only | **Primary execution** |

## Caveats (read before deploying capital)

1. **3.5-month data window.** All metrics are extrapolated from
   2026-01-21 → 2026-05-04. The 5m archive in `data/dxy/dxy_5m.csv` caps at
   20k bars; getting a multi-year 5m DXY history is the single highest-value
   data improvement. Until then, treat Sortino +6 as "did well in this
   window," not as a steady-state expectation.

2. **Scheme C peak exposure ≈ 14× during bearish-FLD bursts.** At 1% risk per
   1× position with 5× bearish scaling and ~3 concurrent bearish entries,
   notional exposure can hit 14× capital. Verify margin/leverage at the
   broker before deploying.

3. **No daily-regime overlay yet.** The 5m layer here ignores daily Scheme
   D. The intended stack (Step 4 wiring) is: daily FLD bias gates 5m entries
   — skip 5m signals when daily FLD = "bullish (all 3 cycles below price)."
   Without that overlay, the strategy will take 5m longs in clear daily
   uptrends and miss the daily-filter selectivity that earned Scheme D its
   Sortino +5.75.

4. **MTM assumes infinite intraday liquidity.** DXY futures are liquid but
   verify fill behavior on T3 exits during news (NFP, FOMC). Slippage during
   those windows will exceed the modeled 3 bps.

5. **Strict-M thresholds were calibrated, not re-validated OOS.** The
   30/72/72 trio came from the highest-trade-count cell of a 27-cell grid.
   That's borderline paper-fitting; a longer 5m archive would let us split
   in-sample (calibrate) vs out-of-sample (validate) properly.

## Code

- Engine: [`src/rsi_pattern/intraday.py`](../src/rsi_pattern/intraday.py)
- MTM: [`src/rsi_pattern/risk_metrics.py`](../src/rsi_pattern/risk_metrics.py)::`build_equity_curve_mtm`
- Runner: [`scripts/h14_intraday_backtest.py`](../scripts/h14_intraday_backtest.py)
- Equity figure: [`figures/09_intraday_equity_curves.png`](../figures/09_intraday_equity_curves.png)
