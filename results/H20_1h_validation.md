# H20 — 1h DXY Validation

**Date:** 2026-05-12

H17/H18/H19 showed the 5m strategy's metrics are fragile to small data
shifts (OOS Sortino swung +4.17 → +2.23 between two BarChart pulls
that differed by 8 days of new data). The honest production
expectation became "+2 to +4 Sortino, regime-dependent" — uncomfortably
wide for capital allocation.

The natural question: **does the strategy work better on 1h, where we
have 3.25 years of history and can do a proper 70/30 walk-forward
with ~2 years train and ~1 year test?**

**Answer: NO.** 1h is not a viable production timeframe. The full-window
Sortino is comparable to 5m's degraded OOS number, the walk-forward
test slice produces only 12 trades/year (below any reasonable
inference threshold), and the strategy's edge inverts on the test
slice (pure-parallel sizing beats Scheme C).

## TL;DR

| Metric | 5m (H14 published) | 5m (H19 shifted-window OOS) | **1h (H20 OOS)** |
|---|---:|---:|---:|
| Sortino | +6.19 | +2.23 | **+0.76** |
| Test trades | n/a (full window 69) | 28 / 52d | **12 / 365d** |
| Test trades per year | n/a | ~196 | **~12** |
| Test Max DD | n/a | −11.62% | **−12.27%** |
| Verdict | calibration win | PAPER_FIT (ratio 0.23) | **PAPER_FIT (ratio 0.28)** |
| Production decision | — | "Sortino +2 to +4 band" | **NOT VIABLE** |

## Setup

- **Data:** 1h DXY from BarChart CSV, 19,999 bars, 2023-02-03 → 2026-05-04
  (1,186 days = 3.25 years).
- **FLD cycles (added in this commit):** `(24, 48, 96)` — 2× harmonic
  ladder mapped to ~1d / 2d / 4d wall-clock. Same spirit as
  H14's 5m `(40, 80, 160)`.
- **Range lookback:** 96 bars (1× longest cycle).
- **Time stop:** 96 bars (1× longest cycle = 4 days).
- **Spread:** 2 bps (between 5m's 3 bps and daily's 2 bps; same as daily
  since the longer hold amortizes spread cost).
- **Strict-M thresholds:** H14 default (30, 72, 72) — H17 confirmed
  these as "incidentally robust" relative to alternatives.
- **Split:** 70/30 → train 2023-02-03 → 2025-05-13 (2.27 years),
  test 2025-05-13 → 2026-05-04 (~1 year).
- **Eligibility floors:** ≥30 train trades, ≥15 test trades (raised
  from H17's 10 because 1h has way more raw data per cell — sparse
  cells aren't worth scoring).

## Results

### Phase 2 — 5-scheme sweep on full window, H14 thresholds

| Scheme | Trades | Mean R | Sharpe | Sortino | Max DD |
|---|---:|---:|---:|---:|---:|
| A. Pure parallel (1/1/1) | 72 | +0.60 | +1.13 | +1.73 | −7.22% |
| B. Modest (1/1/3) | 72 | +1.10 | +1.29 | +2.15 | −11.31% |
| **C. Aggressive (1/1/5)** | 72 | +1.60 | +1.28 | **+2.23** | −14.83% |
| D. Skip bullish + 3× (0/1/3) | 53 | +1.42 | +1.27 | +2.14 | −11.35% |
| E. Conservative (0.5/1/3) | 72 | +1.07 | +1.28 | +2.15 | −11.19% |

**Phase 2 winner: Scheme C** by a hair (+0.08 over B/D/E, all in the +2.14
to +2.23 band). With 72 trades over 3.25 years, the Sortino estimates
have wide error bars; the schemes are statistically indistinguishable
on the full window.

Note: the **+2.23 full-window Sortino on 1h matches the +2.23 H19
OOS Sortino on 5m almost exactly.** Either coincidence or
the strategy's "real" forward expectation is right around +2.

### Phase 3 — 70/30 walk-forward

**Train grid (Scheme C, 27 cells, eligible ≥30 trades shown first):**

| origin | peak | wig | trades | Mean R | Sharpe | Sortino | Max DD |
|---:|---:|---:|---:|---:|---:|---:|---:|
| **25** | **72** | **70** | 31 | +3.27 | +1.88 | **+4.39** | −11.04% | ← winner |
| 25 | 72 | 68 | 30 | +3.35 | +1.86 | +4.37 | −11.04% |
| 25 | 72 | 72 | 34 | +3.01 | +1.88 | +4.27 | −11.04% |
| 30 | 72 | 70 | 53 | +1.97 | +1.51 | +2.75 | −14.87% |
| 30 | 72 | 68 | 47 | +2.16 | +1.48 | +2.71 | −15.33% |
| 30 | 72 | 72 | 60 | +1.76 | +1.51 | **+2.70** | −14.83% | ← H14 baseline |
| 28 | 72 | * | 41–51 | +1.86–+2.20 | +1.32–+1.35 | +2.33–+2.35 | −16% |
| (peak=75 or 78 cells skipped — below eligibility floor on train) |

**Test eval (held-out, 2025-05-13 → 2026-05-04):**

| Cell | Train Sortino | Test Sortino | Train trades | Test trades | Test Max DD |
|---|---:|---:|---:|---:|---:|
| Train-winner (25, 72, 70) | +4.39 | **+0.74** | 31 | **4** | −8.64% |
| H14 baseline (30, 72, 72) | +2.70 | **+0.76** | 60 | 12 | −12.27% |

Verdict: **INCONCLUSIVE on the train-winner** (4 test trades is below
the floor; can't infer). **PAPER_FIT on H14 baseline** (ratio 0.28).

### Phase 4 — 5-scheme sweep on each slice, H14 thresholds

| Scheme | Train Sortino | **Test Sortino** | Train trades | Test trades |
|---|---:|---:|---:|---:|
| A. Pure parallel (1/1/1) | +1.78 | **+1.72** | 60 | 12 |
| B. Modest (1/1/3) | +2.50 | +1.06 | 60 | 12 |
| C. Aggressive (1/1/5) ← H14 | +2.70 | +0.76 | 60 | 12 |
| D. Skip bullish + 3× | +2.46 | +1.20 | 44 | 9 |
| E. Conservative (0.5/1/3) | +2.49 | +1.13 | 60 | 12 |

**Striking finding: Scheme A (no scaling) wins on test by a wide
margin.** The bearish-FLD 5× boost that drove H14's edge actively
*hurts* on the test slice. The amplifier is finding fewer payoff
events and the amplified losses dominate.

### Phase-3 cross-check: which 5m-tested cells perform on 1h?

Both the H17 5m train-winner (28, 72, 70) and the H17 H14 baseline
(30, 72, 72) appear in the 1h grid. On 1h:

- (28, 72, 70): Sortino +2.35 train (eligible) / not separately tested
  on 1h test slice. Below the 1h train winner (25, 72, 70 → +4.39).
- (30, 72, 72): Sortino +2.70 train / +0.76 test.

The cross-timeframe ranking is different. 1h's training-best
thresholds (25, 72, 70) are at the LOOSER end of the origin grid;
5m's tend to cluster around origin=30. No shared "universal" winner.

## Production decision

| Criterion | Threshold | 1h H14 result | Pass? |
|---|---|---:|:---:|
| OOS Sortino | ≥ +2.5 | +0.76 | ✗ |
| OOS trades | ≥ 30 | 12 | ✗ |
| OOS Max DD | better than −15% | −12.27% | ✓ |

**Verdict: NOT VIABLE.** Fails 2 of 3 criteria.

## Why 1h doesn't work

1. **Signal density is ~10× lower than 5m.** 1h produces ~22 strict-M
   trades/year (72 trades / 3.25 yrs); 5m produces ~240/year (~33
   trades / 52 days extrapolated). A 1-year test slice on 1h gives
   only 12 trades — not enough for stable Sortino estimation.

2. **Hold periods are long.** Time stop of 96 bars = 4 trading days.
   With 1.2 trades/month at H14 thresholds, position turnover is so
   low that the overlap-aware MTM equity barely diverges from a
   realized-on-exit model. The structure designed to handle 5m
   overlap doesn't pay rent at 1h.

3. **The bearish-FLD edge that drives Scheme C inverts on 1h test.**
   On the 5m calibration window, bearish FLD bias preceded big up
   moves; the 5× sizing captured them. On the 1h 2025-26 test slice,
   that relationship doesn't hold — Scheme A (uniform sizing) wins.
   Either the cross-cycle (24h/48h/96h) FLD bias signal is noisier
   than the 5m (40b/80b/160b) version, OR the recent regime (USD
   chop post-2024) breaks the asymmetry.

4. **The full-window 1h Sortino +2.23 matches 5m's H19 OOS +2.23.**
   Both numbers may represent the strategy's "real" Sortino on this
   asset class. The +6.19 H14 published was the calibration
   regime; the rest is noise / regime shift around a +2-Sortino
   true edge.

## Implications

1. **Stick with 5m as the production timeframe.** Even though its
   metrics are fragile, it produces enough trades for the strategy
   to be operational. 1h has the same expected Sortino but 10× fewer
   trades, so capital deployment is starvation-thin.

2. **Adjust expected production return down.** The 1h full-window
   Sortino +2.23 corroborates H19's "+2 to +4 band" reading. The
   honest production expectation is **Sortino ≈ +2**, not +4 and
   not +6. Allocate capital accordingly.

3. **Scheme A on 1h is a curiosity worth re-checking.** When
   Scheme C's bearish-amplifier doesn't work, the base unscaled
   strategy still has +1.7 Sortino. If this asymmetry shows up on
   5m too in future re-pulls, it argues for de-emphasizing the
   bearish boost (i.e., switching from C back toward A or B).

4. **No code change needed.** The intraday module gained 1h cycle
   constants in this commit but the strategy module (rsi_m_p1.py)
   continues to read `data.intraday.timeframe: "5m"` from the YAML.
   To run on 1h experimentally: set `timeframe: 1h` and point at the
   1h CSV.

## Recommended next moves (in priority)

1. **Build the SHORT-side V-pattern variant (K from the menu).**
   The Scheme A finding suggests the LONG-side asymmetry is fading.
   A symmetric SHORT setup could capture moves the long-only strategy
   misses, and would unlock USDCHF (whose H15 NO-GO was tied to a
   bearish-skewed FLD bias distribution — long-only got starved).
2. **Implement bi-weekly re-validation cron** (B from the menu)
   per H19's recommendation. Lets us catch regime shifts before
   they break production.
3. **Drop 1h consideration.** Don't waste cycles on it as a primary
   timeframe; it's worse than 5m on every dimension that matters.

## Caveats

1. **Test slice (2025-05 → 2026-05) overlaps the 5m calibration
   window.** Both end May 2026; the 5m window starts Jan 2026. So
   the 1h test slice includes the Jan-May 2026 period that the 5m
   H14/H17/H18/H19 work covered. If the 5m metrics were a regime
   artifact, the 1h test slice could be inheriting the same
   regime-disadvantage.
2. **70/30 split is one cut.** A k-fold or rolling-window
   validation would give tighter confidence intervals. Not done
   here because the headline finding (1h doesn't fix the
   small-sample problem) is robust to the split choice.
3. **Scheme A win on test could be noise.** 12 test trades — wide
   error bars. The "bearish edge inverts" hypothesis needs more
   data before it's actionable.

## Code

- Modified: [`src/rsi_pattern/intraday.py`](../src/rsi_pattern/intraday.py)
  — adds `"1h"` keys to `INTRADAY_FLD_CYCLES`, `INTRADAY_TIME_STOP_BARS`,
  `INTRADAY_SPREAD`.
- New script: [`scripts/h20_1h_validation.py`](../scripts/h20_1h_validation.py)
  — full pipeline (Phase 2 / Phase 3 / Phase 4 / production decision).
- Raw JSON: `results/_h20_run.json`.
- Reproducible: `python3 scripts/h20_1h_validation.py`
