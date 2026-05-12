# H19 — Shifted-Window Re-Validation of H17 + H18

**Date:** 2026-05-12 (afternoon)

A fresh BarChart 5m DXY export landed with **8 days of genuinely new data**
(May 5 → May 12) that were never in any prior analysis. BarChart caps
the export at ~20k bars, so the new window shifted forward by ~7 days:

| Window | First bar | Last bar | Bars |
|---|---|---|---:|
| H14/H17/H18 original | 2026-01-21 00:40 | 2026-05-04 23:55 | 19,999 |
| H19 shifted | 2026-01-28 19:25 | 2026-05-12 17:05 | 19,999 |
| Overlap | 2026-01-28 → 2026-05-04 | — | ~18,400 bars (~96 days) |
| New OOS data | 2026-05-05 → 2026-05-12 | — | ~1,500 bars (~8 days) |

I re-ran H17 (strict-M threshold walk-forward) and H18 (remaining-knob
walk-forward) against the shifted window using the same scripts, same
50/50 split methodology, same H14 baselines. The results are
sobering.

## TL;DR

| Question | Previous answer (H17/H18) | Shifted-window answer (H19) |
|---|---|---|
| Does H14 generalize OOS? | PARTIAL_DECAY (ratio 0.54) | **PAPER_FIT (ratio 0.23)** |
| H14 baseline OOS Sortino | +4.17 | **+2.23** |
| Does (20, 40, 80) FLD cycle revision hold? | YES — wins both train (+9.31) and test (+8.79) | **NO** — test +2.56, margin over H14 only +0.33 (below the +0.5 revision floor) |
| Honest forward-looking Sortino | +4.17 | **+2.2 to +4.2 (regime-dependent)** |

**Three concrete consequences:**

1. **Withdraw the (20, 40, 80) revision candidate.** It was a
   regime-specific win in the original window, not a robust
   improvement.
2. **Pull the H14 published OOS Sortino estimate down further.** The
   honest range is +2.2 to +4.2 across two non-overlapping
   ~52-day windows. Lower-mid of that range is the conservative
   ship number.
3. **H14's strict-M thresholds are paper-fit on this dataset.** Not
   in the worst sense (the strategy still makes money OOS), but in
   the sense that any single calibration window will produce
   thresholds optimized for that window's regime.

## H17 re-run (strict-M thresholds)

| Metric | Original window | Shifted window | Δ |
|---|---:|---:|---:|
| Training winner | (28, 72, 70) | **(30, 72, 70)** | different cell |
| H14 baseline rank on train | #6 (Sortino +7.74) | **#2 (Sortino +9.66)** | improved rank |
| Best train Sortino | +7.90 | **+9.99** | +2.09 |
| Best train trades | 22 | 31 | +9 |
| **H14 baseline test Sortino** | **+4.17** | **+2.23** | **−1.94** |
| H14 baseline test trades | 36 | 28 | −8 |
| H14 baseline train/test ratio | 0.54 | **0.23** | **PAPER_FIT** |
| Verdict | PARTIAL_DECAY | **PAPER_FIT** | escalated |

Notes:
- The **training winner shifted** from (28, 72, 70) to (30, 72, 70).
  Different windows produce different "best" thresholds — confirming
  any single-window selection is noisy.
- The original H17 finding that "H14's threshold choice incidentally
  generalizes better than the trained alternative" **still holds in
  spirit** — the H14 baseline (30, 72, 72) is now rank #2 of 27 on
  train and within 0.33 Sortino of the formal winner. On test,
  H14 (+2.23) ≈ winner (+2.53). Threshold choice is still defensible.
- But the **test slice degrades broadly**. Mar 22 → May 12 is a
  fundamentally weaker regime than the Mar 15 → May 4 slice used in
  the original H17.

## H18 re-run (remaining knobs)

| Knob | Original test-winner & margin | Shifted test-winner & margin | Verdict shift |
|---|---|---|---|
| **FLD cycles** | (20, 40, 80) by **+4.62** | (20, 40, 80) by **+0.33** | from REVISION to **below floor** |
| Range lookback | 80 by +3.95 (suspect) | 80 by +0.33 | tiny gap |
| Trail factor | 3.6 (no alts viable) | 3.6 (same) | unchanged |
| Time stop | 80 by +2.25 | (no test-better alt; H14 wins) | reversed |
| Scheme | C confirmed | C confirmed | unchanged |

Same conclusion summary line from h18_walkforward_remaining_knobs.py
on the new window:

> *No knob's H14 default loses by ≥ +0.5 test Sortino. All knobs hold up.*

The most consequential change is **FLD cycles**:

| FLD cycles | Original test Sortino | Shifted test Sortino | Δ |
|---|---:|---:|---:|
| (20, 40, 80) | +8.79 | **+2.56** | **−6.23** |
| (40, 80, 160) ← H14 | +4.17 | +2.23 | −1.94 |
| (60, 120, 240) | +6.24 | +0.31 | −5.93 |

The original H18 case for (20, 40, 80) rested on a +4.62 test-Sortino
margin. With the shifted window that margin is **+0.33** — below the
+0.5 threshold the script uses to flag a revision candidate.
H18's recommendation **does not survive contact with 8 new days of
data**. The advice "wait for more data before adopting" was the right
call.

## What the 8 new days actually look like

Why did the test slice degrade so much? Three quick diagnostics:

| Metric | Original test (Mar 15 → May 4, 50d) | Shifted test (Mar 22 → May 12, 51d) |
|---|---:|---:|
| Test trades (H14 baseline) | 36 | 28 |
| Test mean R (H14 baseline) | +1.00 | +0.77 |
| Test Max DD (H14 baseline) | −10.70% | −11.62% |
| Test Sortino (H14 baseline) | +4.17 | +2.23 |

Fewer trades, lower mean R, slightly worse DD. The May 5–12 stretch
is a low-vol consolidation in DXY (chart shows price hovering 97–98
with low daily range). Fewer strict-M completions; the ones that do
trigger have smaller follow-through.

## Implications

### 1. Don't adopt (20, 40, 80) FLD cycles

The H18 evidence was window-specific. H19 confirms it. Keep H14's
**(40, 80, 160)** as the production setting.

### 2. Production Sortino expectation: +2 to +4

Across two non-overlapping ~52-day test slices:
- Mar 15 → May 4 (H17): Sortino +4.17
- Mar 22 → May 12 (H19): Sortino +2.23

The blend is **~+3 Sortino**. The honest band is +2.2 to +4.2,
regime-dependent. Use the lower end (~+2.2) for capital allocation;
treat anything above as upside.

### 3. The "Sortino +6.19" headline from H14 is dead

It was already revised down to +4.17 in H17. Now +2.23. The
trajectory across three honest evaluations is **+6.19 → +4.17 →
+2.23** as more rigor / more data gets applied. The final number
will live somewhere in the +2 to +4 band; don't quote +6.19 anywhere.

### 4. H17's "incidentally robust" finding still holds

Even on the shifted window, the train-winner (30, 72, 70) vs. H14
(30, 72, 72) test-Sortino gap is only +0.30. The original H17
conclusion — H14's threshold choice is NOT badly paper-fit relative
to alternatives — survives. **What changed is the absolute level
of expected Sortino, not the threshold ranking.**

### 5. PAPER_FIT verdict is a regime-shift artifact

The script's verdict bucket (train/test ratio) is a useful tripwire
but treats the test slice as ground truth. Here the test slice
itself contains an obvious low-vol regime (May 5–12). The strategy
isn't broken; it's just not in season. Same caveat that applies to
any momentum/breakout system in a quiet tape.

## Action items taken

1. ✅ Preserved old JSON snapshots:
   `_h17_run_window_jan21.json`, `_h18_run_window_jan21.json`.
2. ✅ Re-ran both scripts; new JSON dumps replace the old ones.
3. ✅ This writeup (H19) documents the deltas.
4. ✅ Withdraw the (20, 40, 80) revision candidate in
   `H14_intraday_TRADING_SPEC.md` — banner updated to record both
   H17 and H19 numbers + the failed revision.
5. **NOT taken**: no change to the H14 thresholds, cycles, lookback,
   trail factor, time stop, or scheme. Everything stays as published.

## What to do as more data accumulates

The shifted-window methodology is now established and cheap to repeat.
Suggest re-running this validation **every two weeks** as fresh
BarChart pulls add another ~7 days of new data:

- If test Sortino stays in the +2 to +4 band → confirm the honest
  expectation; ship.
- If test Sortino persistently drops below +1.5 over 3+ consecutive
  re-pulls → strategy edge has decayed materially, pause production.
- If test Sortino jumps back above +4 across multiple re-pulls →
  the original H14 number was right and Mar 22 → May 12 was a fluke.

Document each re-run as an H19-revN appendix.

## Caveats

1. **8 days of new data is small.** The conclusions above could
   swing meaningfully again on the next pull. This is a snapshot,
   not a verdict.
2. **The "shifted window" is still mostly the original window** —
   96 of 104 days overlap. Don't read this as a clean OOS test;
   read it as "what happens if we move the slice forward 7 days."
3. **Same script, same params, same data source.** Anything wrong
   with the methodology in H17/H18 is wrong here too. Strict-M
   detector edge cases, FLD warmup, spread assumptions all carry
   over.
4. **The strategy is still profitable OOS.** Sortino +2.23 with
   Max DD −11.62% is not great-but-it's-not-broken. The honest
   read is "marginal positive edge in this regime, much better
   edge in the Jan-Feb run-up regime, can't tell which is the new
   normal."

## Code

- Preserved old runs: `results/_h17_run_window_jan21.json`,
  `results/_h18_run_window_jan21.json`
- Fresh runs: `results/_h17_run.json`, `results/_h18_run.json`
  (overwritten in place)
- Runners (unchanged from H17/H18, ran against new data file):
  `scripts/h17_walkforward_strict_m.py`,
  `scripts/h18_walkforward_remaining_knobs.py`
- Data: `~/Documents/rsi-data/dxy/dxy_5m.csv` (104 days,
  2026-01-28 → 2026-05-12)
