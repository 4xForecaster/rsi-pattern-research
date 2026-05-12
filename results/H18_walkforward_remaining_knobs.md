# H18 — Walk-Forward of Remaining H14 Knobs

**Date:** 2026-05-12

H17 walk-forward'd the strict-M thresholds. H14 has four more knobs
calibrated on the same 104-day window:

| Knob | H14 value | How it was picked in H14 |
|---|---|---|
| FLD cycles | (40, 80, 160) | "Canonical 2× harmonic ladder" — not formally calibrated |
| Range lookback | 160 bars | Phase 1.4 sensitivity sweep over {0.5×, 1×, 2×} of longest FLD cycle, evaluated on the FULL window |
| Trail activation factor | 3.600× | Inherited from H13 / SURF Fib spec (Dr. A's directive); not data-driven |
| Time stop | 160 bars | Set to 1× longest FLD cycle by convention |
| Scheme | C (1/1/5) | Phase 2.5 sweep over A/B/C/D/E, evaluated on the FULL window |

Plus the meta-question: H14's scheme choice (C over D) was also picked
on the full window. Re-validate.

This step applies the H17 methodology — split 50/50, sweep one knob
at a time on TRAIN with the others held at H14 defaults, evaluate on
TEST.

## Headline

**Three knobs have test-better alternatives.** Of those, **only one
(FLD cycles) wins on BOTH train and test.** The other two
(range lookback, time stop) win on test but lose badly on train,
which is a regime-shift artifact — not a robust improvement.

| Knob | H14 default | Test-best | Margin | Verdict |
|---|---|---|---:|---|
| **FLD cycles** | (40, 80, 160) | **(20, 40, 80)** | +4.62 | **REVISION CANDIDATE** — wins both train and test |
| Range lookback | 160 | 80 | +3.95 | Suspect — lookback=80 had train Sortino +1.45 / DD −44.9%, no train-only rule would pick it |
| Trail factor | 3.6 | 3.6 | 0 | Confirmed (others break the simulator — Sortino −1.4 to −1.9) |
| Time stop | 160 | 80 | +2.25 | Marginal — test gain is real, train loss is small (+7.39 vs +7.74) |
| Scheme | C | C | 0.26 | Confirmed (D close behind on test +3.91; C still wins) |

## Protocol

```
TRAIN = first 50% of bars  → 10,185 bars (2026-01-21 → 2026-03-13)
TEST  = last  50% of bars  →  9,814 bars (2026-03-15 → 2026-05-04)
```

Per knob, sweep its candidate settings on train with everything else
at H14 defaults (including the H17-confirmed strict-M thresholds
30/72/72). Then evaluate each setting on test.

Held constant across all cells: strict-M thresholds (30, 72, 72),
Scheme C multipliers (1, 1, 5) except in the scheme sweep itself,
1% base risk, 3 bps spread, overlap-aware MTM equity, annualization
factor 252×288 = 72,576 bars/yr.

Eligibility: ≥10 train trades **and** ≥5 test trades for a verdict.

## Full results

### FLD cycles

| Cycles | Train trades | Train Sortino | Train Max DD | Test trades | Test Sortino | Test Max DD | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| **(20, 40, 80)** | 33 | **+9.31** | −11.56% | 36 | **+8.79** | −10.13% | **HOLDS_UP** |
| (40, 80, 160) ← H14 | 33 | +7.74 | −13.51% | 36 | +4.17 | −10.70% | PARTIAL_DECAY |
| (60, 120, 240) | 33 | +10.15 | −12.30% | 36 | +6.24 | −16.40% | PARTIAL_DECAY |

**(20, 40, 80) wins both slices.** This is the only revision in
this whole sweep that passes a both-slices filter. It's also a
sensible Hurst pick — the shorter cycles align with what the
literature calls the "infra-trading" 3-5h, 6-12h, 12-24h bands on
5m bars, which match the typical strict-M completion timeline
(~30–60 bars from P1 to RSI<50, roughly 2.5–5 hours).

H14's (40, 80, 160) is a wider lens — it captures slower drift but
under-weights the bar-to-bar mean-reversion that actually drives
strict-M signal quality at 5m.

### Range lookback

| Bars | Train trades | Train Sortino | Train Max DD | Test trades | Test Sortino | Test Max DD | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| 80 | 33 | **+1.45** | **−44.92%** | 36 | **+8.11** | −9.64% | HOLDS_UP |
| 160 ← H14 | 33 | +7.74 | −13.51% | 36 | +4.17 | −10.70% | PARTIAL_DECAY |
| 320 | 33 | +7.50 | −13.51% | 36 | +3.53 | −8.57% | PARTIAL_DECAY |

`lookback=80` is the test-winner but **had a −44.9% drawdown and
Sortino +1.45 on train**. No real-world train-only selection rule
would pick it. The test-win is the test slice's specific
preference for tight ranges (post-Mar-2026 chop), not a property
the strategy can be expected to carry forward.

**H14's 160 stays.** This is a regime-asymmetry artifact, not a
robust improvement. Treat the test-win as a tail of "sometimes
tight ranges work better" rather than evidence to revise.

### Trail activation factor

| Factor | Train Sortino | Test Sortino | Verdict |
|---|---:|---:|---|
| 3.0 | −1.90 | −1.38 | INCONCLUSIVE (both slices lose) |
| **3.6 ← H14** | +7.74 | +4.17 | PARTIAL_DECAY (winning setting) |
| 4.0 | −1.90 | −1.38 | INCONCLUSIVE |

3.0 trails too early (before runners develop), 4.0 trails too late
(past T3, never engages). 3.6 is in the only viable region the
simulator supports. **H14's 3.6 confirmed.**

### Time stop

| Bars | Train Sortino | Test Sortino | Verdict |
|---|---:|---:|---|
| 80 | +7.39 | **+6.41** | HOLDS_UP |
| 160 ← H14 | +7.74 | +4.17 | PARTIAL_DECAY |
| 320 | +8.04 | +1.00 | PAPER_FIT |

`time_stop=80` wins test by +2.25 Sortino. **Train loss is only
−0.35 Sortino.** This is a near-tie on train and a clear win on
test — closer to a true revision candidate than range_lookback,
but smaller margin than FLD cycles. Note also `time_stop=320`
PAPER_FIT verdict — longer hold == best train Sortino, worst test
Sortino, classic over-optimization.

### Scheme

| Scheme | Train Sortino | Test Sortino | Verdict |
|---|---:|---:|---|
| A (1/1/1) | +6.68 | +3.31 | PARTIAL_DECAY |
| B (1/1/3) | +7.69 | +3.85 | PARTIAL_DECAY |
| **C (1/1/5) ← H14** | +7.74 | **+4.17** | PARTIAL_DECAY |
| D (0/1/3) | +6.81 | +3.91 | PARTIAL_DECAY |
| E (0.5/1/3) | +7.32 | +3.90 | PARTIAL_DECAY |

C wins on test by a small margin (+0.26 over D). **H14's C
confirmed**, but only just — D is essentially indistinguishable
within the sample-noise floor.

## What this means for the spec

### The honest one-sentence summary

**H14's FLD cycle choice (40, 80, 160) is empirically inferior to
(20, 40, 80) on this dataset — by Sortino +4.62 on test and +1.57
on train.**

### Why I'm NOT auto-revising the spec

1. **104 days is one window.** A single 50/50 split surfaces the
   candidate but doesn't prove it generalizes forward. The H17
   "PARTIAL_DECAY" finding suggests *every* metric calibrated on
   this window is provisional.

2. **Cycle changes cascade.** If you adopt (20, 40, 80), the
   "lookback = 1× longest cycle" convention says lookback should
   become 80 (the suspect case above) and time_stop similarly 80
   (the marginal case). The three-knob revision is interdependent
   — the test-on-this-data evidence for the pair (lookback=80,
   time_stop=80) is weaker than for cycles alone.

3. **H17's published OOS Sortino (+4.17) was specific to H14's FLD
   cycles.** If we adopt (20, 40, 80), the H17 walk-forward of
   strict-M thresholds should be re-run with the new cycles before
   anyone treats the new Sortino number as definitive. Same paper-
   fit risk that motivated H17, now with one fewer degree of
   freedom but a different anchor.

4. **The standard "ratio ≥ 0.66 = HOLDS_UP" gate is permissive.**
   (20, 40, 80) clears it (8.79 / 9.31 = 0.94), but the absolute
   level (+8.79 test Sortino on 36 trades) is implausibly high
   even by our previous standards. Could be true; could be a
   short-window mirage. Need fresh data.

### Recommended path

1. **Document this finding prominently** (this doc + H14 spec
   banner update).
2. **Defer the revision.** When the next 52 days of 5m data
   accumulate, re-run with (20, 40, 80) FLD cycles + matched
   lookback/time-stop. If the new train-window Sortino is in the
   same range as today's test-window number (+8.0 to +9.0), the
   revision is real and the spec should move to v1.1 with the
   tighter cycles.
3. **Until then, run H14 as published.** The published expected
   Sortino is +4.17 (from H17). Adopting (20, 40, 80) prematurely
   exposes Dr. A to whatever asymmetry made the test slice score
   so well — without certainty it persists.

## Cross-reference to H17

H17 concluded H14's strict-M thresholds (30, 72, 72) have a 0.54
test/train ratio — PARTIAL_DECAY but generalize *better* than the
train-formally-optimized alternative.

H18 finds the same PARTIAL_DECAY verdict for H14's other knobs,
BUT identifies a FLD-cycle alternative that HOLDS_UP. Implication:
the strict-M threshold paper-fit risk H17 caught is downstream of
a larger paper-fit risk on cycle selection. H17's +4.17 OOS Sortino
may itself be optimistic relative to a properly-tuned strategy on
this data — the (20, 40, 80) test Sortino +8.79 suggests so.

But same caveat: 104 days, single split, can't prove it carries
forward.

## Caveats (compounded across H17 + H18)

1. **Multi-knob optimization on one window is structurally biased.**
   Even when each knob is varied in isolation, picking the
   test-better setting for one knob is a form of selection on the
   test slice. Across 4 knobs each with 3 candidates, the
   probability that *some* test-winner is spurious is non-trivial.
2. **Cycle changes invalidate downstream calibrations.** Adopting
   (20, 40, 80) means re-running H14 Phase 1.2 (strict-M grid),
   H14 Phase 1.4 (lookback sensitivity), H14 Phase 2.5 (scheme
   sweep), H17 (threshold walk-forward). Big re-validation
   surface.
3. **Trail factor sweep was incomplete.** Only 3.0/3.6/4.0
   tested. The viable region might extend between 3.4–3.8; I
   didn't sweep finely because the 3.6 default sits squarely in
   it.
4. **Scheme sweep used H14's FLD cycles.** With (20, 40, 80) the
   bias distribution would shift and C-vs-D ranking could flip.
   Re-validate if cycles change.

## Code

- Runner: [`scripts/h18_walkforward_remaining_knobs.py`](../scripts/h18_walkforward_remaining_knobs.py)
- Raw JSON: `results/_h18_run.json` (per-knob train/test cell metrics + revision list)
- Reproducible: `python3 scripts/h18_walkforward_remaining_knobs.py`
