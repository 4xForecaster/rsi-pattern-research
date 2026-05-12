# H17 — Walk-Forward Validation of H14 Strict-M Thresholds

**Date:** 2026-05-12

H14 calibrated strict-M thresholds `(origin=30, peak=72, wiggle=72)` on
the **same 104-day window** it then evaluated on. The Phase 1.2 grid
sweep picked the loosest topology-respecting cell (yielded the most
trades, 69), and Phase 2.5 reported Sortino +6.19 on Scheme C against
that same window. This is structurally a paper-fit risk: thresholds
that produced 69 trades have a sample-size advantage that any
narrower combo can't compete with on the same window.

This step addresses it directly:

1. Split the 104-day window 50/50 — train Jan 21 → Mar 13, test
   Mar 15 → May 4.
2. Sweep the **same 3×3×3 strict-M grid** on TRAIN only. Score each
   cell by Sortino under Scheme C. Require ≥10 train trades for
   eligibility (avoids picking 2-trade outliers).
3. Apply the train-winning thresholds to TEST. Report the full metric
   stack on both slices.
4. Also evaluate **H14's published thresholds** (30, 72, 72) on both
   slices — directly visible apples-to-apples.

## TL;DR — verdict

| Metric | Train winner (28/72/70) | H14 baseline (30/72/72) |
|---|---:|---:|
| Train Sortino | **+7.90** | +7.74 |
| Test Sortino | **+2.78** | **+4.17** |
| Train/Test ratio | 0.35 | **0.54** |

- **Walk-forward winner = (28, 72, 70)**, not H14's (30, 72, 72). But
  the train-winner *overfits* — on test, it drops to Sortino +2.78
  (ratio 0.35), while H14's baseline drops to +4.17 (ratio 0.54).
- **H14's full-window Sortino +6.19 IS optimistic.** The held-out
  test slice produces +4.17. The +6.19 was approximately a
  trade-weighted blend of the train-regime (+7.74) and test-regime
  (+4.17) results.
- **H14's threshold choice itself is NOT paper-fit in the worst
  sense.** Even though it wasn't formally trained, it generalizes
  *better* than the formally-trained alternative on this OOS split.
  Interpretation: the trade-count selection rule from H14 Phase 1.2
  was accidentally robust because looser thresholds (more trades)
  reduce overfit susceptibility.

**Verdict: PARTIAL_DECAY** (test/train Sortino ratio 0.35–0.54,
falls in the [0.33, 0.66) "real edge that decays" bucket).

## Protocol

```
TRAIN  = first 50% of bars  →  10,185 bars  (2026-01-21 → 2026-03-13)
TEST   = last  50% of bars  →   9,814 bars  (2026-03-15 → 2026-05-04)
```

Grid (matches H14 Phase 1.2):
- `origin ∈ {25, 28, 30}`
- `peak   ∈ {72, 75, 78}`
- `wiggle ∈ {68, 70, 72}`

Held constant: Scheme C multipliers (1/1/5), FLD cycles (40, 80, 160),
range lookback 160 bars (pre-P1), structural stop, SURF Fib targets,
trail at 3.600×, time-stop 160 bars, spread 3 bps, 1% base risk,
overlap-aware MTM equity, annualization factor 252×288 = 72,576 bars/yr.

Eligibility filter: cells with <10 train trades excluded from
winner selection (too few for stable Sortino).

## Full TRAIN grid results

| origin | peak | wiggle | trades | Mean R | Sharpe | **Sortino** | Max DD | note |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 28 | 75 | 68 | 8 | +1.32 | +5.25 | +7.91 | −2.37% | skip (<10) |
| **28** | **72** | **70** | **22** | **+3.54** | **+5.06** | **+7.90** | **−13.31%** | **winner** |
| 28 | 75 | 70 | 9 | +3.08 | +4.88 | +7.88 | −5.01% | skip |
| 28 | 72 | 72 | 27 | +2.97 | +5.03 | +7.85 | −13.31% | |
| 30 | 72 | 70 | 28 | +3.00 | +4.97 | +7.77 | −13.51% | |
| 30 | 72 | 72 | 33 | +2.61 | +4.95 | +7.74 | −13.51% | **H14 baseline** |
| 28 | 75 | 72 | 10 | +2.67 | +4.52 | +7.28 | −5.01% | |
| 28 | 72 | 68 | 20 | +2.80 | +4.51 | +7.27 | −9.68% | |
| 30 | 72 | 68 | 26 | +2.38 | +4.47 | +7.15 | −10.61% | |
| 28 | 78 | * | 2 | +10.13 | +4.32 | +7.08 | −4.50% | skip |
| 25 | 75 | 68 | 3 | +2.09 | +4.61 | +6.78 | −2.44% | skip |
| 25 | 75 | 70 | 3 | +2.09 | +4.61 | +6.78 | −2.44% | skip |
| 30 | 75 | 70 | 14 | +2.09 | +4.26 | +6.73 | −5.67% | |
| 25 | 72 | 68 | 10 | +4.55 | +4.14 | +6.68 | −9.56% | |
| 30 | 78 | * | 4 | +5.19 | +3.92 | +6.48 | −5.02% | skip |
| 30 | 75 | 72 | 15 | +1.89 | +3.95 | +6.22 | −5.67% | |
| 25 | 72 | 70 | 11 | +3.68 | +3.05 | +4.66 | −13.31% | |
| 25 | 72 | 72 | 12 | +3.29 | +2.86 | +4.38 | −13.31% | |
| 30 | 75 | 68 | 13 | +0.94 | +2.87 | +4.17 | −4.08% | |
| 25 | 75 | 72 | 4 | +1.32 | +2.64 | +3.81 | −3.92% | skip |
| 25 | 78 | * | 0 | n/a | n/a | n/a | 0.00% | skip |

The top of the leaderboard is **tight** — 8 cells within 1 Sortino-point
of each other. With only 10–33 train trades, that gap is well inside
the sample-noise floor; the "winner" is barely distinguishable from
H14's baseline on the train slice. That's a clue the held-out
performance will be the discriminating signal.

## Apples-to-apples comparison

| Slice | (28, 72, 70) train-winner | (30, 72, 72) H14 baseline |
|---|---:|---:|
| Train trades | 22 | 33 |
| **Train Sortino** | **+7.90** | +7.74 |
| Train Mean R | +3.54 | +2.61 |
| Train Max DD | −13.31% | −13.51% |
| Test trades | 22 | **36** |
| **Test Sortino** | **+2.78** | **+4.17** |
| Test Mean R | +0.99 | +1.00 |
| Test Max DD | −9.59% | −10.70% |
| **Test/train Sortino ratio** | **0.35** | **0.54** |

Key reads:

1. **H14 has more trades both train (33) and test (36).** Looser
   thresholds → wider sample → more stable Sortino estimate.
2. **The train-winner's edge is concentrated in Mean R (+3.54 vs
   +2.61).** That's where the overfit lives — the 22-trade slice
   happened to contain bigger winners under tighter thresholds. On
   test, Mean R reverts to ~+1.00 for both — the same outcome from
   different selection rules.
3. **Both configs decay OOS.** Train Sortinos ~+7.8 are not
   sustainable. Test Sortinos +2.8–+4.2 are the steady-state
   expectation.

## Comparison to H14's published Sortino +6.19 (full window)

H14 reported Sortino +6.19 on the full 104-day window using (30, 72,
72). Walk-forward reveals:

- The full-window number was a trade-weighted blend of the **train
  regime (~+7.74)** and **test regime (~+4.17)**.
- Trade count split: 33 train + 36 test = 69 full (matches H14's
  published 69).
- **+6.19 is unreliable as a forward-looking expectation.** The
  test-only number (+4.17) is the honest read.

This is not a strategy failure — Sortino +4.17 is still a strong
result. It IS a calibration-honesty failure: the published number
was optimistic by ~33%.

## Recommendation

1. **Keep H14's threshold choice (30, 72, 72).** It's NOT paper-fit
   relative to alternatives in the same grid; it actually generalizes
   better than the train-optimized pick. The trade-count selection
   rule was a happy accident.
2. **Revise H14's expected-Sortino number from +6.19 → +4.17** in
   the production spec. Banner added to
   [H14_intraday_TRADING_SPEC.md](H14_intraday_TRADING_SPEC.md).
3. **Don't run a wider grid search.** The top-9 cells cluster
   within 1 Sortino-point at the sample-noise floor. Searching
   harder will just inflate the optimism further.
4. **Re-validate on the next 52 days** as the data accumulates.
   The honest decay test repeats forward: keep a rolling 52-day
   train / 52-day OOS pair and require the OOS Sortino to stay >2.0
   to keep the strategy live.

## Caveats

1. **Single train/test split.** The 50/50 cut is arbitrary; a
   k-fold or rolling-window validation would give tighter confidence
   intervals. Not done here because the entire data window is 104
   days — there's not enough to fold meaningfully without
   re-using bars.
2. **Test slice contains a slow-tape period.** Mar 15 → May 4
   includes the spring 2026 USD consolidation, which is a different
   regime from the strong USD downtrend of the train slice.
   Decay is partly regime-shift, not strictly paper-fit. Both
   matter for production sizing.
3. **22-trade test sample.** Sortino at n=22 has wide error bars.
   The +2.78 vs +4.17 gap between configs may itself be noise.
4. **Did NOT re-tune the FLD cycles, lookback, or trail factor.**
   Only strict-M thresholds were swept. The other knobs were locked
   to H14's spec — they're also calibrated on the same window,
   carry the same paper-fit risk, but the user instruction said
   "If H14 doesn't survive, banner H14_intraday_TRADING_SPEC.md and
   stop." Not extending scope.

## Code

- Runner: [`scripts/h17_walkforward_strict_m.py`](../scripts/h17_walkforward_strict_m.py)
- Raw JSON: `results/_h17_run.json` (full 27-cell grid + train/test metrics)
- Reproducible: `python3 scripts/h17_walkforward_strict_m.py`
