# Run 1 Results — Hypothesis Tests H1-H4

**Date:** 2026-05-12
**Instrument:** DXY only
**Timeframes:** daily / 4h / 1h / 5m
**Detection config:** `PatternConfig` defaults (peaks ≥65, troughs ≤35, max_span=30 bars, max_completion=30 bars)
**Data:**
- Daily: 9,304 bars (1990-01-02 → 2026-05-04, ~36 years)
- 4h: 3,084 bars (2024-05-10 → 2026-05-04, 724 days)
- 1h: 19,999 bars (2023-02-03 → 2026-05-04, 1,186 days)
- 5m: 19,999 bars (2026-01-21 → 2026-05-04, 103 days)

## H1 — Detection quality

**Status:** Not formally tested in run 1 (would require manual visual labeling). Detector produced sensible-looking M and V regions on the synthetic test fixtures (5 pytest tests pass).

## H2 — Fractal self-similarity

**Result: PARTIAL support — proportionally fractal, not strictly time-scaled.**

### State occupancy (% of bars)

| State | Daily | 4h | 1h | 5m |
|---|---|---|---|---|
| M | 17.5% | 17.4% | 19.1% | 17.5% |
| V | 17.2% | 19.4% | 18.2% | 14.8% |
| C | 65.4% | 63.2% | 62.8% | 67.8% |

Remarkably consistent across timeframes — strong proportional self-similarity.

### State duration KS tests (calendar-time)

All pairs significantly different (p ≈ 0). State durations measured in calendar-time do NOT scale uniformly across timeframes. **The pattern is not strictly time-fractal** — an M on daily isn't a stretched M on 5m.

### Transition matrix chi-squared (across timeframe pairs)

| Pair | chi² | p-value |
|---|---|---|
| daily vs 4h | 0.91 | 0.999 |
| daily vs 1h | 13.24 | 0.104 |
| daily vs 5m | 0.20 | 1.000 |
| 4h vs 1h | 8.59 | 0.378 |
| 4h vs 5m | 1.01 | 0.998 |
| 1h vs 5m | 13.38 | 0.099 |

Transition probabilities are statistically indistinguishable across most timeframe pairs (p > 0.1). The state machine has **scale-invariant transition probabilities** even though absolute durations differ.

### Interpretation

The M/C/V framework is **proportionally fractal**: state occupancy and transition probabilities are invariant across timeframes. Absolute calendar-time durations are not — slower timeframes have proportionally longer absolute durations, as expected. This is the natural form of fractal behavior for an oscillator, not the trivial form.

## H3 — Conditional forward returns

**Result: SIGNALS REAL BUT TINY. Direction differs across timeframes.**

### Significant findings (KS p < 0.05, full table in appendix)

**Daily timeframe (n=1,625 M observations, 1,597 V observations):**

| State | Horizon | Mean fwd return | Cohen's d |
|---|---|---|---|
| M | 5d | +0.12% | +0.110 |
| M | 20d | +0.37% | +0.169 |
| M | 60d | +0.75% | **+0.182** |
| V | 5d | -0.09% | -0.083 |

**M state predicts MODESTLY POSITIVE forward returns on daily DXY** — opposite of naive "RSI overbought → sell" intuition. This is consistent with momentum continuation: when RSI is forming a topping pattern, DXY tends to keep rising before reversing.

**1h timeframe (n=3,812 M observations):**

| State | Horizon | Mean fwd return | Cohen's d |
|---|---|---|---|
| M | 20h | -0.02% | -0.045 |
| M | 60h | -0.05% | -0.060 |

Direction is opposite to daily — on 1h, M predicts mildly negative returns.

**5m timeframe (n=3,491 M observations):**

| State | Horizon | Mean fwd return | Cohen's d |
|---|---|---|---|
| M | 60×5m | -0.02% | -0.088 |
| V | 60×5m | -0.04% | -0.170 |

Both M and V predict modestly negative forward returns — likely a regime artifact (5m data only covers Jan-May 2026).

### Interpretation

- **All effect sizes are small** (|d| < 0.2). Statistical significance is driven by large sample sizes (n in the thousands).
- **Direction of M effect FLIPS** between daily (+) and intraday (-). The pattern's directional content is not stable across timeframes.
- **The strongest single effect** is V on 5m → negative forward returns (d = -0.170). May be regime-specific.
- **The visual M-as-top-as-sell intuition is empirically wrong on daily DXY.** Daily M predicts continuation higher, not reversal lower.

This is a real falsification of a naive contrarian interpretation. The pattern is descriptive (state machine valid), but not robustly predictive of direction.

## H4 — Markov vs. HMM

**Result: Markov chain is sufficient. Hidden states add no value.**

### Markov 1h transition matrix (n=19,998 transitions)

```
        C       M       V
C    0.978   0.012   0.011
M    0.038   0.962   0.000     ← M → V never happens directly
V    0.037   0.000   0.963     ← V → M never happens directly
```

**Direct M↔V transitions are exactly zero.** The state machine matches theory: M → C → V → C → M. C is a mandatory intermediate.

### Markov vs. HMM (1h)

| Model | Log-likelihood | Free params | BIC |
|---|---|---|---|
| **Markov (3 states)** | **-2,738.0** | **6** | **5,535** |
| HMM K=2 | -18,362 | 6 | 36,783 |
| HMM K=3 | -18,362 | 12 | 36,843 |
| HMM K=4 | -2,735.3 | 20 | 5,669 |
| HMM K=5 | -2,731.1 | 30 | 5,759 |

**Markov wins on BIC by 134 units over the best HMM.** The K=2 and K=3 HMMs failed to converge to a useful solution. K=4 and K=5 found similar fits to Markov but with 3-5x more parameters.

### Interpretation

The observed M/C/V labels capture all of the predictive state-transition dynamics. No hidden regime structure improves over the direct labels. This is a clean result: the user's visual classification of states ARE the dynamics, not noisy projections of something deeper.

## Summary table

| Hypothesis | Result | Confidence |
|---|---|---|
| H1: Detection works | Synthetic tests pass; no manual validation yet | Medium |
| H2: Fractal self-similarity | Partial — proportional yes, time-scaled no | High |
| H3: Conditional forward returns | Tiny effect sizes; direction flips across TFs | High (negative finding) |
| H4: State-transition predictability | Markov sufficient; HMM adds nothing | High |

## Implications for downstream products

1. **The M/C/V framework is a valid state classifier.** Use it as a labeling layer, not a directional signal.
2. **On daily timeframe, M state has weak momentum-continuation bias** (d = 0.18). Not strong enough alone but could compound with other signals.
3. **Direct M ↔ V never happens.** Any downstream model that uses these states can rely on this invariant (no need to handle M-to-V edge case).
4. **State-transition timing is predictable** via Markov chain. Forecasting "when will the current state end" is well-modeled.

## Recommended next steps

1. **Visual labeling for H1.** Hand-label 50-100 patterns on a sample DXY chart to formally measure detector precision/recall against ground truth.
2. **Threshold tuning.** Defaults (≥65, ≤35) may be too aggressive. Iterate on the threshold values and watch how the H3 effect sizes move.
3. **Event-conditional forward returns.** Instead of forward returns conditional on state OCCUPANCY (the bar IS in M), try forward returns conditional on state TRANSITION events (the bar is at M COMPLETION). The completion event is where predictive value is most likely concentrated.
4. **Regime-conditional H3.** The direction flip between daily and intraday may reflect different market regimes. Test H3 within sub-periods (rate-hike cycles, risk-off windows).
5. **Confluence with Hurst FLD.** The mechanical edges here are small. Combined with Hurst directional bias, they may produce a usable composite signal.

## Reproducing this run

```bash
git clone https://github.com/4xForecaster/rsi-pattern-research
cd rsi-pattern-research
pip install -e .
# Drop CSVs at data/dxy/dxy_{daily,4h,1h,5m}.csv
jupyter notebook notebooks/01_dxy_exploration.ipynb
```

Or scripted (see `results/run1_script.py` if added).

## Files modified in run 1

- `src/rsi_pattern/data.py` — added support for BarChart "Latest" column name (some exports use "Latest" vs older "Last")
- `src/rsi_pattern/patterns.py` — fixed `summarize()` groupby index ambiguity
- `tests/test_patterns.py` — 5 smoke tests, all pass
