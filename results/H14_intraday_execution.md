# H14 — Intraday Execution Layer (5m / 15m DXY)

**Date:** 2026-05-12

The M-P1 strategy ported from daily to intraday timeframes with strict-M
detection, intraday Hurst FLD cycles, and overlap-aware mark-to-market
equity. Daily Scheme D (H11/H12/H13) is retained as a regime/bias layer
only — H14 becomes the top-of-stack execution layer.

## TL;DR

| Layer | Timeframe | Scheme | Trades | Sortino | Max DD | Status |
|---|---|---|---|---|---|---|
| Execution (primary) | **5m** | **C. Aggressive (1/1/5)** | 69 | **+6.19** | −13.5% | Production |
| Execution (secondary) | 15m | C (baseline) or v_all (loose+pre-entry) | 18 / 84 | +3.28 / +13.76 | −15.2% / −15.1% | Caveated — 18 trades is below the 20-trade validity floor for strict-M; loose-M cell with pre-entry range needs out-of-sample retest before adoption |
| Regime filter | Daily | D. Skip bullish + 3× bearish | 56 | +5.75 | −2.8% | Unchanged (H13 v1.1) |

**Production recommendation (5m)**: strict-M (origin<30, peaks≥72, wiggle≥72) →
P1+1 entry LONG → range = `high(P1) − min(low) over [P1−160, P1)` →
structural stop → SURF Fib 1.618/2.236/3.618 → trail at 3.600× → time-stop 160
bars → FLD bias from cycles (40, 80, 160) → **Scheme C multipliers**
(bullish 1×, neutral 1×, bearish 5×) → 1% risk per 1× position → 3 bps spread.

## ⚠️ Read this before the rest

The 5m and 15m data on disk covers **only 2026-01-21 → 2026-05-04 (~104 days,
20k 5m bars / 6.7k 15m bars)**. All annualized metrics in this document are
extrapolations from a 3.5-month window. Sortino +6 and MAR +47 are *real for
the period* but should NOT be taken as steady-state expectations. The
strategy's ranking across schemes/knobs is the load-bearing finding here, not
the absolute levels.

Independent confirmation requires a longer 5m/15m archive. Step 4 of the
hardening plan (integration with hurst-agent) should plumb in a longer-history
data source before this becomes production-rated.

## Phase 1 — Recon & Calibration

### 1.1 Data coverage

| TF | Source | Bars | Start | End | Span |
|---|---|---:|---|---|---:|
| 5m | BarChart CSV | 19,999 | 2026-01-21 00:40 UTC | 2026-05-04 23:55 UTC | 104 days |
| 15m | resampled from 5m (OHLC agg) | 6,705 | 2026-01-21 00:30 UTC | 2026-05-04 23:45 UTC | 104 days |

Resample rule: `5m → 15min` with `first/max/min/last/sum` on
open/high/low/close/volume. Standard.

### 1.2 Strict-M threshold calibration

Default strict-M (origin<30, peaks≥75.01, wiggle≥70) produced **31 trades on
5m and 8 on 15m** — both far below the 100-trade target. Ran the full
3×3×3 grid sweep over `origin_max ∈ {25, 28, 30}`, `peak_min ∈ {72, 75, 78}`,
`wiggle_min ∈ {68, 70, 72}`:

| TF | Max trade count | At thresholds | Topology check |
|---|---:|---|---|
| 5m | 69 | origin=30 / peak=72 / wiggle=72 | ✓ — origin below 30 (deep low), peaks ≥72 (still in overbought zone), wiggle ≥72 (shallow wiggle by construction) |
| 15m | 18 | origin=30 / peak=72 / wiggle=72 | ✓ — same combo; just hits the data-window ceiling |

**Note on `wiggle=72`** — counterintuitively, *raising* the wiggle floor from
70 to 72 *increases* trade counts. That's because in `detect_strict_m` the
wiggle floor is the threshold that *ends* a top-zone visit: a higher floor
breaks the upper zone into more separate Ms rather than merging them.
`wiggle=72` is therefore both the highest-yielding *and* most morphologically
strict choice (shallow wiggle = stays high between peaks).

**Verdict**: Even the loosest topology-respecting combo doesn't reach 100
trades. The bottleneck is the data window, not the thresholds. Adopting
origin=30 / peak=72 / wiggle=72 as calibrated intraday strict-M parameters.

### 1.3 FLD cycle re-calibration

Checked `~/Documents/4xForecaster/hurst-agent/src/hurst_agent/cycles.py`: only
`DAILY_PERIODS = {signal: 10, mid: 20, sequence: 40}` is defined; no intraday
canonical map. Using the user-proposed 2× harmonic ladder:

| TF | Cycles (bars) | Cycles (wall-clock) |
|---|---|---|
| 5m | (40, 80, 160) | 3h 20m / 6h 40m / 13h 20m |
| 15m | (32, 64, 128) | 8h / 16h / 32h |

These are passed to `fld.fld_bias(df, cycles=...)`. The bias rule
(bullish = all 3 cycles' price > FLD; bearish = all 3 below; neutral = mixed)
is unchanged from daily.

### 1.4 Range lookback sensitivity (Scheme D, strict-M, structural stop)

| TF | Lookback | Bars | Trades | Mean R | Sharpe | **Sortino** | Max DD | Total R/yr |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 5m | 0.5× | 80 | 46 | +1.83 | +1.54 | +2.36 | −32.60% | +304.74 |
| 5m | **1×** | **160** | 46 | +1.68 | +3.64 | **+5.52** | **−9.17%** | +279.64 |
| 5m | 2× | 320 | 46 | +1.43 | +3.56 | +5.31 | −9.17% | +237.60 |
| 15m | **0.5×** | **64** | 15 | +1.69 | +2.01 | +2.97 | −11.52% | +142.31 |
| 15m | 1× | 128 | 15 | +1.69 | +2.01 | +2.97 | −11.52% | +142.31 |
| 15m | 2× | 256 | 15 | +0.49 | +0.26 | +0.35 | −12.92% | +41.15 |

**5m winner: 1× = 160 bars.** 0.5× collapses Sortino (the 80-bar floor
catches mid-session price wiggle, not the actual rise-origin); 2× is mildly
worse (older, stale floor).

**15m: 0.5× ≡ 1×** within rounding — the trough almost always sits within
the first 64 bars before P1 for this sample. Taking **0.5× = 64 bars** as
the spec'd default since it's the smaller, more responsive window with
identical metrics.

## Phase 2 — Full Sweep & Ablation

### 2.5 Five-scheme position-sizing sweep

Run on calibrated config (strict-M, structural stop, pre-P1 range with
chosen lookback). Overlap-aware MTM equity curve (`build_equity_curve_mtm`
in `risk_metrics.py`), spread = 3 bps on 5m / 2.5 bps on 15m, annualization
factor = 252×288 = 72,576 bars/yr on 5m and 252×96 = 24,192 on 15m.

#### 5m (lookback=160, 69 strict-M completed trades; FLD bias: 38 neutral / 23 bullish / 8 bearish)

| Scheme | Trades | Mean R (wtd) | Total R/yr | Sharpe | **Sortino** | Calmar | MAR | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A. Pure parallel (1/1/1) | 69 | +0.91 | +227.67 | +3.42 | +4.98 | +31.34 | +24.77 | −7.37% |
| B. Modest (1/1/3) | 69 | +1.34 | +335.03 | +3.98 | +6.02 | +51.31 | +40.68 | −9.17% |
| **C. Aggressive (1/1/5)** | **69** | **+1.77** | **+442.38** | **+4.03** | **+6.19** | **+59.62** | **+47.51** | **−13.51%** |
| D. Skip bullish + 3× (0/1/3) | 46 | +1.68 | +279.64 | +3.64 | +5.52 | +36.51 | +30.69 | −9.17% |
| E. Conservative (0.5/1/3) | 69 | +1.23 | +307.33 | +3.84 | +5.82 | +43.49 | +35.51 | −9.17% |

**5m winner: Scheme C.** Sortino +6.19, beats D by +0.67. **Different from
daily.** Bullish-FLD entries on 5m contribute net-positive R (8 bearish-FLD
trades aren't enough to carry a "skip bullish" rule; you need the 23
bullish-FLD trades' contribution). 5× bearish scaling adds enough on those 8
bearish-FLD trades to dominate the comparison.

#### 15m (lookback=64, 18 strict-M completed trades; FLD bias: 11 neutral / 3 bullish / 4 bearish)

| Scheme | Trades | Mean R (wtd) | Total R/yr | Sharpe | **Sortino** | Calmar | MAR | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A. Pure parallel (1/1/1) | 18 | +0.43 | +41.43 | +0.41 | +0.60 | +0.60 | +0.53 | −11.19% |
| B. Modest (1/1/3) | 18 | +1.29 | +124.60 | +1.67 | +2.46 | +5.01 | +4.30 | −12.09% |
| **C. Aggressive (1/1/5)** | **18** | **+2.15** | **+207.76** | **+2.18** | **+3.28** | **+8.76** | **+7.32** | **−15.15%** |
| D. Skip bullish + 3× (0/1/3) | 15 | +1.69 | +142.31 | +2.01 | +2.97 | +6.55 | +5.59 | −11.52% |
| E. Conservative (0.5/1/3) | 18 | +1.35 | +130.31 | +1.85 | +2.73 | +5.77 | +4.93 | −11.77% |

**15m would-be winner: C.** Same ranking as 5m. **But 18 trades is below
the 20-trade validity floor.** Treat 15m baseline as informational, not
production. See ablation below for an alternate 15m config that crosses the
threshold.

### 2.7 Three-knob ablation on Scheme C

#### 5m

| Cell | Trades | Mean R | Total R/yr | Sharpe | **Sortino** | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| **baseline (strict / struct / pre-P1)** | **69** | +1.77 | +442 | +4.03 | **+6.19** | **−13.5%** |
| v1 loose-M | 254 | +1.98 | +1,785 | +3.13 | +5.48 | −55.6% |
| v2 wider ATR stop | 69 | +1.77 | +442 | +4.03 | +6.19 | −13.5% |
| v3 pre-entry range | 69 | +7.67 | +1,914 | **−0.56** | **−0.70** | **−281.9%** |
| v_all | 253 | +3.47 | +3,113 | +1.74 | +2.65 | −44.7% |

**5m winner: baseline.** Sortino +6.19 beats every alternative.
- **v1 (loose-M)** ramps trade count 4× but Max DD blows out to −55.6% (5×
  bearish scaling on noisier loose-M signals is catastrophic).
- **v2 (wider ATR stop)** is identical to baseline — ATR(14) on 5m is
  always tighter than the 160-bar structural floor, so the wider-of rule
  never bites.
- **v3 (pre-entry range)** is **broken** on 5m. The M's inner trough is
  much smaller than the 160-bar pre-P1 floor, so initial stops collapse and
  5× scaling on losers produces a −282% Max DD. Demonstrates that pre-entry
  range works on daily (per H13) but NOT at 5m. Different timescale, different
  rule.

#### 15m

| Cell | Trades | Mean R | Total R/yr | Sharpe | **Sortino** | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| baseline (strict / struct / pre-P1) | 18 | +2.15 | +208 | +2.18 | +3.28 | −15.2% |
| v1 loose-M | 83 | +1.28 | +377 | +3.30 | +4.46 | −22.3% |
| v2 wider ATR stop | 18 | +2.15 | +208 | +2.18 | +3.28 | −15.2% |
| v3 pre-entry range | 18 | +4.17 | +409 | +3.27 | +6.82 | −13.6% |
| **v_all (loose + wider + pre-entry)** | **84** | **+3.26** | **+979** | **+6.64** | **+13.76** | **−15.1%** |

**15m surprise: v_all wins decisively** — Sortino +13.76 (vs +3.28
baseline), 84 trades (crosses the validity floor), Max DD basically
unchanged from baseline at −15.1%. The 15m timescale apparently rewards
the loose-M detector + M-inner-trough range + ATR-floor stop combination.

This is a different optimum than 5m. Two plausible reads:
1. **Real**: 15m has different dynamics (longer hold times, different signal
   density) and genuinely prefers a different config.
2. **Sample-size artifact**: only 84 trades over 3.5 months annualized to
   Sortino +13.76 — extreme number that's almost certainly inflated by the
   short window.

**Without longer 15m history, this finding is suggestive but not
production-rated.** Recommendation: deploy 5m baseline as the primary
execution layer; treat 15m v_all as a hypothesis to revisit when more data
is available.

## Final selection

| Layer | TF | Detector | Range rule | Stop rule | Lookback | Scheme | Notes |
|---|---|---|---|---|---:|---|---|
| Execution (primary) | **5m** | strict-M (30/72/72) | pre-P1 | structural | 160 | **C (1/1/5)** | Production-rated within data-window caveat |
| Execution (secondary) | 15m | strict-M (30/72/72) | pre-P1 | structural | 64 | C (1/1/5) | 18 trades — informational |
| 15m alt (hypothesis) | 15m | loose-M | pre-entry | wider-ATR | 60 (default) | C (1/1/5) | Sortino +13.76, 84 trades — re-test on longer history before deploying |
| Regime filter | Daily | loose-M | pre-P1 | structural | 60 | D (0/1/3) | Unchanged from H13 v1.1; used as a confluence/bias overlay, not for entry timing |

## Differences from daily Scheme D (worth knowing)

| Dimension | Daily (H12/H13) | 5m (H14) |
|---|---|---|
| Detector | Loose-M | Strict-M (calibrated 30/72/72) |
| Winning scheme | D (skip bullish) | C (5× bearish, keep all) |
| FLD cycles | (10, 20, 40) | (40, 80, 160) |
| Range lookback | 60 bars (≈ 2.7 months wall-clock) | 160 bars (≈ 13.3 hours) |
| Time stop | 200 bars (≈ 9 months) | 160 bars (≈ 13.3 hours) |
| Spread | 2 bps | 3 bps |
| Equity curve | Realized-on-exit only | Overlap-aware MTM |
| Trade overlap | Rare (peak 8 concurrent) | Common — MTM is mandatory |

## Caveats

1. **Short data window dominates everything.** 104 days at 5m is a fortunate
   regime sample (USD chop with a major bearish leg in Feb). All metrics
   would shift on a different window. Sortino +6 is real for this slice, not
   a steady-state expectation.

2. **15m at 18 trades is below the 20-trade validity floor.** Baseline 15m
   numbers are documented for completeness but not production-rated. The
   alternate 15m config (loose + pre-entry, 84 trades) crosses the floor
   but inverts every knob vs. 5m — re-test before adopting.

3. **Pre-entry range broke on 5m (−282% Max DD).** This is the inverse of
   H13's daily finding where pre-entry range was the highest-Mean-R cell.
   The takeaway: range definition is timescale-dependent. Don't generalize
   the H13 "pre-entry might be a Scheme F variant on daily" finding to
   intraday.

4. **MTM equity is bias-clean but assumes infinite intraday liquidity.**
   Position-sizing per 1% risk with potentially overlapping positions
   implies real capital deployed up to 14× during peaks (Scheme C's
   bearish-FLD periods). Verify margin/leverage with the broker.

5. **No regime overlay yet.** The 5m execution layer here doesn't filter
   by daily FLD bias / Scheme D regime. Step 4 of the hardening plan should
   add: only take 5m entries when daily FLD bias agrees (or at least when
   daily FLD ≠ "bullish, all 3"). Expect this to trade off some return
   for higher win rate.

## Code

- New module: [`src/rsi_pattern/intraday.py`](../src/rsi_pattern/intraday.py)
  — calibrated constants, ATR(14), pattern iteration, range/stop rules,
  fib-to-MTM conversion.
- MTM equity: `build_equity_curve_mtm` added to
  [`src/rsi_pattern/risk_metrics.py`](../src/rsi_pattern/risk_metrics.py).
- Backtest runner: [`scripts/h14_intraday_backtest.py`](../scripts/h14_intraday_backtest.py)
  — reproduces Phase 1.4, 2.5, 2.7 in one go.
- Spec: [`results/H14_intraday_TRADING_SPEC.md`](H14_intraday_TRADING_SPEC.md).
- JSON params: [`results/h14_intraday_spec_params.json`](h14_intraday_spec_params.json).
- Raw run dump: [`results/_h14_run.json`](_h14_run.json).
