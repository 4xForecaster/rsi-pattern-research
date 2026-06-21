# H30 — Box-Pattern Backtest with Corrected Spec

**Date:** 2026-06-20
**Module:** [`src/rsi_pattern/box_pattern.py`](../src/rsi_pattern/box_pattern.py)
**Tests:** [`tests/test_box_pattern.py`](../tests/test_box_pattern.py) — **8/8 pass**
**Script:** [`scripts/h30_box_pattern_corrected.py`](../scripts/h30_box_pattern_corrected.py)
**Run dump:** [`results/_h30_run.json`](_h30_run.json)
**Figures (regenerated):** [`figures/26_box_examples_dxy.png`](../figures/26_box_examples_dxy.png),
[`figures/27_box_history_dxy.png`](../figures/27_box_history_dxy.png)
**Compare against:** [`results/H29_box_pattern_validation.md`](H29_box_pattern_validation.md) (preserved)

## TL;DR — corrections made, GBPUSD flips to SWEEP after H30b detector fix (still 0/7 GO)

The H29 implementation had two material errors flagged by Dr. A. Both
are fixed:
- **T1/2 endpoint:** now `(P0 + P2)/2` (was `(P0 + P3)/2`). Translation
  now reads rally vs correction *only*, with the breakout phase
  excluded — cleaner per Hurst's third law.
- **Detector mega-box cap:** `max_length = 250 bars` (was unbounded).
  The 1024-bar 2022→2026 DXY SHORT box surfaced in the H29 follow-up
  visuals is gone, and the dedup behaviour around skipped mega-boxes
  now correctly enumerates the sub-boxes those mega-boxes were eating.

Two target ladders were tested side-by-side per Dr. A's spec:
- **Variant A** (primary). *Original*: `1.618 / 2.345 / 3.456 × box.height`,
  anchored on P2, trail at the default 3.600× entry-anchored (effectively
  never armed since A's T3 sat far closer to entry than B's). *Tightened
  2026-06-20*: TWO targets `(1.618, 2.236) × height`, T3 dropped; trail
  activates at `P2 + 2.200·height` (mirror of B's "3.600 near 3.618" but
  P2-anchored because A's targets aren't entry-anchored).
- **Variant B** (alternative, unchanged): `1.618 / 2.236 / 3.618 × box.height`,
  anchored on P1, trail at entry + 3.600 × range (M-P1 convention).

**Both variants still produce 0/7 GO at the locked thresholds**, but the
**failure mode shifted** — H29 failed primarily on OOS trade count
(thin universes); H30 has healthy OOS trade counts (18–32 per pair) and
fails on OOS Sortino: most pairs are slightly negative, none clears the
+1.0 NO-GO floor. The box-pattern single-trade-trigger application is
**robustly NO-GO** on FX daily — the corrected spec rules out
"H29 was underpowered" as an explanation. **The detector is good; the
trade-trigger framing is wrong**, exactly as Hurst's
cross-scale-pressure framing predicted.

## Detector sanity — corrected spec produces ~3–6× more boxes

The max-length cap fixes a subtle artifact: an uncapped mega-box was
consuming its dedup window, hiding many shorter sub-boxes inside it.
With `max_length=250` the mega-box is skipped without advancing
`last_p3`, so the sub-boxes enumerate properly.

| Symbol | H29 long | H30 long | H29 short | H30 short |
|---|---:|---:|---:|---:|
| DXY    |  34 | **170** |  67 | **160** |
| EURUSD |  51 | **119** |  57 | **128** |
| GBPUSD |  51 |  **97** |  59 | **117** |
| USDJPY |  24 | **142** |  88 | **158** |
| USDCAD |  20 | **123** |  68 | **103** |
| AUDUSD |  87 | **129** |  21 | **120** |
| NZDUSD |  83 | **122** |  28 | **122** |

This is the expected effect of the cap; it is **not** parameter tuning,
and it does not change any per-box semantics. It only changes how many
boxes the detector reports.

## Per-pair results (LONG boxes only, the trade-trigger arc)

OOS Sortino (and trade count) for each variant, with the H29 single
number shown for the delta read.

A-old = the original H30 variant A (3 targets, no effective trail).
A-new = the 2026-06-20 tightening (2 targets, trail near T2_A). B is
unchanged.

| Symbol | H29 OOS / n | A-old OOS / n | **A-new OOS / n / MDD** | Δ (A-new − A-old) | B OOS / n / MDD | A-new vs B |
|---|---|---|---|---:|---|---|
| DXY    | −0.46 /  3 | −0.78 / 29 | **−0.90 / 29 / −17.8%** | **−0.12** (hurt) | −0.89 / 31 / −18.7% | tie |
| EURUSD |   n/a /  0 | −1.42 / 29 | **−1.48 / 29 / −22.0%** | **−0.06** (hurt slightly) | −1.20 / 32 / −24.2% | B better |
| GBPUSD | −1.21 /  2 | −0.70 / 18 | **−0.38 / 18 / −6.4%** | **+0.32** (helped) | −0.56 / 18 / −9.4% | **A-new better** |
| USDJPY | −0.76 /  2 | −0.40 / 28 | **−0.63 / 28 / −11.3%** | **−0.23** (hurt) | −0.39 / 30 / −10.0% | B better |
| USDCAD | +0.43 /  4 | −0.17 / 19 | **+0.11 / 19 / −5.6%** | **+0.28** (helped, sign flip) | −0.12 / 21 / −7.0% | **A-new better** |
| AUDUSD | −0.19 /  6 | +0.32 / 32 | **+0.61 / 32 / −8.3%** | **+0.29** (helped) | +0.70 / 32 / −9.0% | B better |
| NZDUSD | −1.65 /  6 | −0.12 / 28 | **−0.59 / 28 / −10.7%** | **−0.47** (hurt) | +0.10 / 29 / −10.7% | B better |

**Did the cut help or hurt Variant A?** **Mixed, net trivial.** Mean
Δ across the 7 pairs = **+0.01**; median Δ = **−0.06**. Three pairs
were helped (GBPUSD, USDCAD, AUDUSD — and USDCAD flipped from −0.17
to +0.11), four pairs were hurt (DXY, EURUSD, USDJPY, NZDUSD; NZDUSD
the worst at −0.47). The early trail activation IS doing something
visible: **A-new's OOS MaxDD is better than B's on 5 of 7 pairs**
(DXY −17.8 vs B −18.7, EURUSD −22.0 vs −24.2, GBPUSD −6.4 vs −9.4,
USDCAD −5.6 vs −7.0, NZDUSD −10.7 = tie). So the trail is protecting
drawdown the way Dr. A intended — but on Sortino the right-tail cost
(when a runner that would have gone to A-old's 3.456× gets trail-
stopped earlier) partly washes out the drawdown win.

**Variant ranking after the tightening: B still edges A-new** on
Sortino — wins 4 of 7 pairs (EURUSD, USDJPY, AUDUSD, NZDUSD), loses 2
(GBPUSD, USDCAD), ties 1 (DXY). On MaxDD the ranking flips: A-new
wins 5 of 7. Neither clears GO on any pair.

H24 robustness gate not invoked anywhere — no pair cleared the GO
prerequisite.

Variant ranking on OOS Sortino across pairs (a tie-breaker for any
future H31 use of either target ladder): in the **original H30 cut**
Variant B slightly edged Variant A on 6 of 7 pairs; after the
**2026-06-20 A-tightening** B still wins 4 of 7 on Sortino and A-new
wins 5 of 7 on MaxDD. The interpretation is structural — Variant B
anchors targets on P1 (higher than P2) so targets sit further from
entry; A-new's earlier trail activation protects drawdown by ratcheting
the stop near T2_A. Neither is enough to flip any pair to a tradeable
edge.

## Comparison to H29: did the correction change the trade set?

**Yes, materially** — but not in a way that flips the verdict.

- **Aligned-box count multiplied 10–30×.** DXY: H29 aligned 6 → H30
  aligned 121 (variant A). USDJPY: H29 aligned 2 → H30 aligned 90.
  USDCAD: H29 aligned 2 → H30 aligned 88. The corrected T1/2 sits left
  of the legacy (since P2 < P3), so more P1s now qualify as right of
  T-mid → bullish. Combined with the cap-induced detector boost, the
  aligned-trade universe grew massively.
- **Statistical power is much better.** H29 had trade counts of 2–14
  per pair, leaving every result vulnerable to "small n." H30 has
  56–109 *full-sample* trades per pair, 18–32 *OOS* — well above the
  10-trade NO-GO floor on 6 of 7 pairs. The NO-GO verdict can no longer
  be blamed on thin samples.
- **OOS Sortinos converged toward zero.** H29 ranged −1.65 to +0.78
  full-sample; H30 ranges −1.42 to +0.70. The mean is ≈ −0.4 on H30
  and ≈ −0.5 on H29 — slightly better, still negative.

The corrections **did exactly what they were supposed to do**: clean
the translation read, prevent mega-box artifacts, and provide enough
trade-count power that the negative is a real negative, not a
sample-size artifact.

## Decision (load-bearing, autonomous)

- **No hurst-agent change.** 0/7 GO under both variants → the box-
  pattern *trade-trigger* application is shipped NO-GO with high
  confidence (statistical power is no longer a complaint about the
  result).
- **The detector is kept and improved.** It now passes 8 unit tests
  and renders cleaner visuals (no mega-box) — a stronger research
  asset than before. Future agents that *aggregate* boxes (rather
  than trade them one by one) get a better substrate.
- **H29 results preserved.** Both the markdown and `_h29_run.json` are
  unchanged on disk and remain valid as the H29 snapshot. The H29
  script (`h29_box_pattern_validation.py`) is now stale — it will
  produce different numbers if re-run because the module defaults
  changed. The H29 results doc + json on disk are the authoritative
  H29 record; the H29 script is left in place but should be considered
  the H29-era snapshot of intent, not a reproducer.
- **H31 (regime classifier via translation aggregation) remains the
  recommended next step** per `docs/BOX_PATTERN_APPLICATIONS.md`. H30
  closes the trade-trigger arc; the cross-scale aggregation use is
  *unchanged* by H30's outcome — if anything strengthened, because
  the corrected detector produces more boxes and so a denser
  aggregation signal.

## Net read

The corrected spec is implemented faithfully (8/8 tests; one new unit
test per correction). Detection is cleaner and more granular. Both
target variants still fail to produce a tradeable edge on any of the
7 FX majors, with healthy statistical power that rules out the
"small-n" alibi. **The single-box trade trigger is dead** —
regardless of T1/2 endpoint, target ladder, or detector cap. The
detector itself is in better shape than it was after H29, ready for
the cross-scale H31 use.

## Detector algorithm correction (H30b, 2026-06-20)

Dr. A flagged a real, structural bug in the detector after the visual
examples landed. The original algorithm nominated P1 from a pre-computed
``scipy.signal.find_peaks`` list and locked it at the FIRST local
extremum after P0. On a dominant impulse with intermediate prominent
peaks (the 2008 DXY rally: P0 ≈ 75.7 in Sep '08, intermediate peak ≈ 82
in early Oct, dominant peak ≈ 88 in late Oct), the legacy code locked
P1 at 82 and ran the rest of the geometry off the wrong opposite swing.

### Fix

**P1 must be the highest extreme reached between P0 and the bar where
price first retraces 50% of the running impulse — NOT a pre-identified
local peak.**

The corrected algorithm is implemented in
``box_pattern._detect_box_corrected``. Walk forward from each P0
candidate, maintaining a running extreme (max-high for LONG, min-low
for SHORT). At each bar:

1. If a new running extreme, update.
2. Otherwise, check invalidation **first** (new lower low for LONG,
   new higher high for SHORT) — if hit, the candidate dies and a new
   P0 spawns at the current bar (the new lower low / higher high). The
   spec's "lower low forms *before* the 50% retrace triggers" pins this
   ordering.
3. Otherwise, compute the 50% retrace level from the *current* running
   extreme and check if the bar pierces it. If so, P1 locks at the
   running extreme; P2 locks at the current bar; search forward for P3.

The legacy detector remains addressable via ``legacy=True`` for H29 /
H30a reproducibility.

### Load-bearing implementation choice — single candidate at a time

The brief suggested "concurrent candidate P0s, first to trigger wins."
Implemented literally this gives the smaller, structurally less
meaningful box: an intermediate ``find_peaks`` trough between the deep
P0 and the dominant peak triggers its own 50%-retrace EARLIER (because
its retrace level is higher relative to a shallower P0) and steals the
box. That contradicts Dr. A's 2008 stated intent (he wants P0 = Sep '08,
not the intermediate Oct-16 trough). The corrected algorithm therefore
processes one P0 candidate at a time, in earliest-first order; new
``find_peaks`` candidates are only consulted when the current candidate
is dropped (invalidation, abandonment at ``max_length``, or box
completion at P3). Invalidation respawn (new lower low becomes the
new P0 immediately) is preserved.

### Unit-test coverage

14/14 pass. Three new tests specifically target the failure modes:
- `test_corrected_detector_preserves_deep_p0_when_legacy_jumps_to_intermediate`
- `test_corrected_detector_short_preserves_deep_p0`
- `test_corrected_detector_invalidates_old_p0_when_deeper_low_forms`
plus `test_legacy_flag_round_trips` to verify legacy=True still reproduces the H29/H30a path.

### Impact on the 7-pair backtest

The corrected detector grew the LONG universe ~3× per pair (DXY 170 →
275, USDJPY 142 → 201, USDCAD 123 → 182) because boxes that were
previously eaten by the now-removed mega-box dedup and by the
legacy-locked-at-first-peak P1 path now properly enumerate as their
own (deeper) structures. With more (and structurally larger) boxes,
OOS Sortinos shifted materially:

| Symbol | A H30a OOS | **A H30b OOS** | Δ | B H30a OOS | **B H30b OOS** | Δ |
|---|---:|---:|---:|---:|---:|---:|
| DXY    | −0.90 / 29 | **−0.23 / 30** | +0.67 | −0.89 / 31 | **−0.12 / 30** | +0.77 |
| EURUSD | −1.48 / 29 | **+0.44 / 22** | +1.92 | −1.20 / 32 | **+0.70 / 22** | +1.90 |
| GBPUSD | −0.38 / 18 | **+1.78 / 20** | +2.16 | −0.56 / 18 | **+0.41 / 20** | +0.97 |
| USDJPY | −0.63 / 28 | **−0.17 / 26** | +0.46 | −0.39 / 30 | **−0.45 / 26** | −0.06 |
| USDCAD | +0.11 / 19 | **−0.41 / 22** | −0.52 | −0.12 / 21 | **−0.51 / 22** | −0.39 |
| AUDUSD | +0.61 / 32 | **−0.37 / 19** | −0.98 | +0.70 / 32 | **−0.48 / 19** | −1.18 |
| NZDUSD | −0.59 / 28 | **−0.81 / 20** | −0.22 | +0.10 / 29 | **−0.91 / 20** | −1.01 |

Six of seven pairs sit closer to zero on Variant A (most −0.81 to +0.44,
the rest at +1.78). **GBPUSD Variant A flips NO-GO → SWEEP** at
OOS Sortino **+1.78 on 20 OOS trades** — first crossing of the +1.0
NO-GO floor anywhere in the box-pattern arc, but well below the +3.0 GO
floor and below the H24 robustness gate's thin-OOS trigger (still 20
trades < 30 cap). Variant B trails A on Sortino (5 of 7 pairs) and on
MaxDD — A continues to be the better of the two ladders after the
detector fix.

### Verdict

Still **0/7 GO under either variant**. The detector fix is correct and
visible in the figures (no mega-box; the 2008-style false-P1 cases are
gone; the recent-5 DXY panel shows clean structural geometries). GBPUSD
is the only pair whose Sortino crossed the +1.0 NO-GO floor; not enough
to ship. The H31 regime-classifier direction remains the right move —
the detector substrate is now ~3× denser (544 DXY boxes vs 330 before)
and structurally cleaner.

### Figures re-rendered with H30b detector

The five existing PNGs (figures 26, 27, 28, 29, 30) have been
regenerated with the corrected detector. The recent-5 DXY panel
(figure 26) now shows boxes 3–218 bars long instead of the H30a
artifact 1024-bar mega-box. Full-history overview (figure 27)
records 544 detected boxes (275 long, 269 short, vs H30a's 330).
Multi-timeframe examples (figures 28, 29, 30) similarly updated. All
re-copied to `~/Documents/4xForecaster/`.

## Box chaining and reversal (H30c, 2026-06-20)

Dr. A extended the box construction rule with two new behaviours:

1. **Same-direction chaining.** After a box confirms at P3, the P2 of
   that box can become the P0 of a next-box in the same direction. If
   the standard 4-point construction triggers from there, box-2 of the
   chain is born (P0_2 = P2_1, then standard running max → 50% retrace
   → P3 above P1). Chains can extend arbitrarily.
2. **Reversal detection.** A bullish chain ends when an inverse
   (bearish) box develops with its P0 anchored at the **terminal high**
   reached during the bullish chain (the running max across the whole
   chain, including post-P3 extensions). Mirror for bearish chains.

Implemented as ``box_pattern._detect_box_chained`` and wired through
``detect_boxes_df(chain_mode=True)``. After each confirmed box, a
continuation candidate (P0 = previous P2, same direction) races against
a reversal candidate (P0 = chain's running terminal extreme, opposite
direction). Whichever confirms first wins. Each emitted box carries
``chain_id``, ``chain_index`` (0 = first of chain), and
``reverses_chain_id`` (set on the first box of every chain that
reversed a prior one). The H30b standalone detector is preserved at
``chain_mode=False`` (the default) — H30b numbers reproduce.

### Unit tests (4 new, 18/18 total pass)

- `test_three_box_long_chain_each_p2_becomes_next_p0` — 3-box LONG
  chain, asserts `P0_2 = P2_1` and `P0_3 = P2_2`.
- `test_long_to_short_reversal_anchored_at_chain_terminal_high` —
  reversal box's P0 sits at the chain's terminal high, with
  `reverses_chain_id` pointing back.
- `test_short_to_long_reversal_anchored_at_chain_terminal_low` —
  mirror.
- `test_chain_mode_off_returns_no_chain_metadata` — back-compat.

### DXY chain shape (full history)

| Metric | Value |
|---|---:|
| Total chained boxes (long + short) | 397 |
| Number of distinct chains | 198 |
| Reversal-started chains | 197 |
| Longest single chain (boxes) | 3 |
| Most common chain length | 2 |

Most chains are pairs (a LONG box reverses to a SHORT, or vice versa)
with frequent short reversal sequences in noisy stretches. The longest
chains run to 3 boxes — there's no DXY 5+box continuation in 36 years
of daily data at the current swing prominence. That itself is
informative: dominant impulses rarely chain through more than two
continuation legs before a reversal triggers.

### Chain-conditional backtest

[`scripts/h30c_chain_conditional.py`](../scripts/h30c_chain_conditional.py)
runs Variant A across four lenses per pair:
- **H30b baseline** — standalone single-direction detector (chain_mode=False).
- **N≥1** — all chained boxes (both directions), no chain filter.
- **N≥2** — continuation boxes only (skip the first box of every chain;
  trade only when at least one prior box of the chain has already
  confirmed).
- **N≥3** — extra-strict; trade only when ≥2 prior boxes have confirmed.

Same H12 metric stack, same 70/30 OOS split, locked GO/SWEEP/NO-GO
rules. H24 robustness gate would fire on any GO; none did.

| Sym | H30b OOS / n | N≥1 OOS / n | N≥2 OOS / n | N≥3 OOS / n |
|---|---|---|---|---|
| DXY    | −0.23 / 30 | **+2.14 / 43** | **+3.34 / 17 SWEEP** | +0.12 / 7 |
| EURUSD | +0.44 / 22 | −0.54 / 27 | −0.39 / 16 | −0.35 / 8 |
| GBPUSD | +1.78 / 20 | +0.50 / 29 | +0.74 / 12 | +1.90 / 4 |
| USDJPY | −0.17 / 26 | −0.05 / 32 | +0.03 / 21 | **+1.32 / 11 SWEEP** |
| USDCAD | −0.41 / 22 | −0.41 / 21 | −0.86 / 14 | −1.12 / 11 |
| AUDUSD | −0.37 / 19 | +0.78 / 26 | +0.18 / 19 | +0.37 / 14 |
| NZDUSD | −0.81 / 20 | −0.69 / 36 | −0.39 / 25 | −0.35 / 18 |

### Did chain context help?

**Mixed, but DXY shows the clearest improvement Dr. A predicted.**

- **DXY responds strongly to chain context.** OOS Sortino lifts from
  −0.23 at standalone H30b to **+3.34 at N≥2** (the headline finding;
  +3.57 above baseline). N≥2 trade count is 17, which is over the
  10-trade NO-GO floor but under the 30-trade GO floor — so it ships as
  **SWEEP, not GO**. The locked rule binds on trade count, not Sortino;
  one more OOS year of DXY history would likely tip it to GO. N≥1 also
  beats baseline (+2.14 vs −0.23) at a sample of 43 OOS trades. Tight
  on the GO floor (+3.0). At N≥3 the trade count crashes to 7 and the
  result is uninterpretable.
- **USDJPY also responds at N≥3** (+1.32 SWEEP) — chain context flips
  the standalone NO-GO to a SWEEP at the strictest lens. Smaller
  sample (11 OOS trades).
- **AUDUSD lifts off the floor at N≥1** (+0.78 vs baseline −0.37). Not
  enough to clear NO-GO but the direction is right.
- **GBPUSD regresses.** The standalone H30b result (+1.78 SWEEP) was
  the strongest pair-baseline result anywhere in the box arc, and
  chain context erodes it (N≥1 +0.50, N≥2 +0.74) — for GBPUSD, the
  *first* box of each chain was carrying the signal, not the
  continuations.
- **EURUSD, USDCAD, NZDUSD** are NO-GO across all four lenses; chain
  context doesn't rescue them.

**0 (pair × lens) cells clear GO.** Three cells clear SWEEP under chain
filters (DXY N≥1, DXY N≥2, USDJPY N≥3) — first time any chain-filter
cell has crossed the +1.0 NO-GO floor.

### What this means

The H29/H30b standalone-box strategy was robust NO-GO with high
statistical power. The H30c chain-conditional lens partially confirms
Dr. A's intuition: chain context matters for at least DXY (Sortino jumps
from −0.23 to +3.34) and modestly for USDJPY and AUDUSD. But it isn't
universal — GBPUSD's H30b SWEEP came from standalone first-of-chain
boxes, and the cross-symbol majority is unmoved.

The DXY result is the most actionable. **It is not GO under the locked
rule** (17 < 30 OOS trades), but the Sortino crosses the +3.0 floor —
the *only* pair × lens cell in the box arc that has. This is consistent
with H31's premise (regime classifier via translation aggregation):
chain context partially substitutes for the cross-scale framing the
Hurst canon requires, and DXY — the program's most-studied pair — is
where the substitution works best.

**No hurst-agent change.** 0 GO. Live cron untouched. Chain detector
kept as a unit-tested research asset; H31 regime-classifier work can
build on either chain-mode aggregation (`chain_index ≥ K` filter) or
the lighter-touch translation aggregation already proposed.

### Figures re-rendered with chain coloring (H30c)

- [figures/26_box_examples_dxy.png](../figures/26_box_examples_dxy.png) — recent-5 boxes colored by chain (green family for LONG chain stages, red family for SHORT, blue/purple for reversals); chain ID and chain index annotated in each panel title.
- [figures/27_box_history_dxy.png](../figures/27_box_history_dxy.png) — full DXY history overlay. Reversal markers `P` (→LONG) and `X` (→SHORT) added to the legend; chain summary in the title.
- [figures/28/29/30_box_*_examples_5tf.png](../figures) — all three multi-timeframe panels regenerated with chain metadata in the per-panel annotation block (`Chain: id=N, index=K[, REVERSES chain M]`).

All five PNGs re-copied to `~/Documents/4xForecaster/`.

## H30d (2026-06-20) — two further detector bugs Dr. A caught from the H30c figures

Two real bugs surfaced when Dr. A reviewed the regenerated H30c
figures. Both diagnosed and fixed. The H30d backtest invalidates the
H30c "DXY N≥2 +3.34 SWEEP" headline; that was bug-driven inflation
from now-eliminated micro-boxes.

### Bug 1 — P3 marker plotted at the wrong price level

Dr. A's statement: "Point-3 level always is equal to point-1 level."

`BoxPattern.p3_price` was storing the bar's actual high (LONG) or low
(SHORT) at P3 — diagnostic across the recent-5 DXY panels showed
deltas of ±0.07 to ±0.67 vs `p1_price`. Renderers using `box.p3_price`
as the marker's y-coordinate were plotting P3 at the bar's intra-bar
extreme rather than at P1's threshold level.

**Fix:** `_build_box` / `emit_box` now set `p3_price = p1_price`. The
field's docstring is updated to reflect this. The bar's actual high/low
at P3 remains recoverable from the source OHLC data. Renderers in
`scripts/h30_box_visuals.py` and `scripts/h30_visual_examples_5tf.py`
use `box.p3_price` directly — no chart-script changes needed; markers
now sit at the P1 level.

### Bug 2 — micro-boxes (P1 collapsing to P0 = a 1-bar swing)

Dr. A's statement: "the box is shallower than price action in all
charts."

Diagnostic dump on the recent-5 DXY panels: **4 of 5 boxes had
`P1_idx == P0_idx`**. The "box" was a 1-bar intra-bar range, not a real
swing — exactly the shallow-box symptom Dr. A flagged.

Root cause: the corrected detector initialized `running_max = high[P0]`
(LONG) and used that for the 50% retrace level computation. If no
post-P0 bar ever exceeded P0's high (a flat / down stretch), the
retrace level stayed at `(low[P0] + high[P0]) / 2` = the mid of the P0
bar's intra-bar range. The first subsequent bar whose low pierced that
level fired the retrace check, locking P1 at P0. Result: a 1-bar
micro-box whose "height" was the P0 bar's intra-bar range, typically
much smaller than the surrounding price action.

**Fix:** gate the 50% retrace check on a new flag `re_updated` that
flips True only when running_max actually advances PAST P0's own value.
If no post-P0 bar exceeds P0's high (LONG) / low (SHORT), the candidate
abandons (or is invalidated by a new lower low / higher high) instead
of collapsing to a micro-box. Applied to all three corrected code
paths: `_detect_box_corrected` (standalone), `_walk_first_box` (chain
first-box), `_walk_chain_continuation` (cont + rev tracks). Legacy
detector unaffected (it uses `find_peaks` for P1 which is prominence-
vetted and immune to this bug).

### Regression tests (2 new, 20/20 total pass)

- `test_bug2_no_p1_equals_p0_micro_box_when_running_max_never_updates_first` —
  on a fixture where bars 6–15 stay strictly inside the P0 bar's range,
  the detector must NOT emit a P1==P0 micro-box; it must wait for the
  real dominant peak at idx 30.
- `test_bug1_p3_price_equals_p1_price_for_rendering` — asserts
  `box.p3_price == box.p1_price` on every emitted box (both standalone
  and chain mode).

### Verification on real DXY data

| Metric | H30c (buggy) | H30d (fixed) |
|---|---:|---:|
| Total chained boxes | 397 | **265** |
| Boxes with `p3_price == p1_price` | 0 | **265 / 265 ✓** |
| Micro-boxes (`p1_idx == p0_idx`) | 132 | **0 ✓** |

132 micro-boxes were eliminated — Dr. A was right that the visuals
showed shallow boxes; the detector was generating them.

### Backtest impact — H30c headlines invalidated

**H30b standalone (Variant A) OOS Sortino — bug-corrected:**

| Sym | H30c (buggy) | **H30d (fixed)** | Δ |
|---|---:|---:|---:|
| DXY    | −0.23 / 30 | **−0.61 / 40** | −0.38 |
| EURUSD | +0.44 / 22 | **−0.17 / 25** | −0.61 |
| GBPUSD | +1.78 / 20 | **+1.24 / 24** SWEEP | −0.54 |
| USDJPY | −0.17 / 26 | **−0.15 / 29** | +0.02 |
| USDCAD | −0.41 / 22 | **−0.29 / 26** | +0.12 |
| AUDUSD | −0.37 / 19 | **−0.30 / 20** | +0.07 |
| NZDUSD | −0.81 / 20 | **−0.97 / 23** | −0.16 |

Most pairs shifted modestly. GBPUSD A holds at SWEEP (+1.24 down from
+1.78) — still the only positive Sortino at standalone H30b. No new
GOs.

**H30c chain-conditional (Variant A) — bug-corrected:**

| Sym | H30b H30d | N≥1 OOS | N≥2 OOS | N≥3 OOS |
|---|---|---:|---:|---:|
| DXY    | −0.61 / 40 | +0.35 / 36 | **+0.34 / 27** (was +3.34) | +0.57 / 20 |
| EURUSD | −0.17 / 25 | −1.32 / 26 | −1.15 / 21 | −0.97 / 17 |
| GBPUSD | +1.24 / 24 | +0.76 / 12 | +1.42 / 7 | +1.03 / 4 |
| USDJPY | −0.15 / 29 | −0.53 / 8 | −0.75 / 4 | −0.53 / 2 |
| USDCAD | −0.29 / 26 | +0.78 / 41 | +0.36 / 36 | +0.05 / 29 |
| AUDUSD | −0.30 / 20 | −0.28 / 26 | −0.40 / 22 | −0.63 / 20 |
| NZDUSD | −0.97 / 23 | −0.48 / 29 | −0.58 / 23 | −0.61 / 16 |

**The H30c headline "DXY N≥2 +3.34 SWEEP" was bug-inflated.** With the
detector fixed, DXY N≥2 lands at **+0.34 / 27 NO-GO**. USDJPY N≥3 +1.32
SWEEP also gone (now −0.53). **0 GO cells, 0 SWEEP cells** across the
entire (pair × lens) matrix after bug-fixes — vs H30c's claimed 0 GO,
3 SWEEP.

The honest verdict at H30d: **the box-pattern strategy is decisively
NO-GO on every pair at every lens** when the detector doesn't
manufacture micro-box noise. Dr. A's catch prevented an unfounded
"DXY chain context lifts Sortino over the GO floor" claim that would
have driven H31 design.

### Visuals re-rendered with H30d detector

All 5 PNGs regenerated and re-copied to `~/Documents/4xForecaster/`:
- `figures/26_box_examples_dxy.png` — recent-5 panels now show boxes
  with multi-bar swings (5–96 bars range). No more P1=P0 collapses.
  P3 markers sit exactly at P1's level.
- `figures/27_box_history_dxy.png` — 265 boxes (was 397). Chain shape
  visibly cleaner.
- `figures/28/29/30_box_*_examples_5tf.png` — multi-timeframe panels
  refreshed.

### Net read

H30d is a *bug-fix* update, not a strategy-change update. Dr. A's catch
exposed a detector defect that was inflating the H30c chain-conditional
result on DXY (+3.34 → +0.34) and producing visually shallow boxes
across every panel. With the fixes, the box-pattern arc is
unambiguously NO-GO across H30b standalone, H30c chain-conditional, and
H30d bug-corrected — and 20/20 unit tests including regression coverage
for both bugs. The legacy detector (H29 / H30a) is unaffected (it uses
`find_peaks` for P1, immune to the micro-box mechanism). The H31
regime-classifier remains the recommended direction; the box detector
is a cleaner research substrate after H30d but its single-trigger
trade strategy is robustly dead.

## H30e (2026-06-20) — third detector bug Dr. A caught: P0 not at deepest low

Dr. A's third catch in the H30d figures: "Black arrow shows price's
lowest-low which is where point-0 should rest in a bullish scenario."
The detector locked P0 at a shallower swing low while a deeper low
existed within the [P0..P1] impulse window.

### Diagnostic

Over the 265 H30d-corrected DXY boxes, **103 (39%) violated the
"P0 = lowest low in [P0..P1]" rule**:

| Direction | Violators | Worst delta |
|---|---|---|
| LONG  | 69 / 165 | 5.42 (chain_id=5 idx=2: P0_price=88.28, actual min low=82.86) |
| SHORT | 34 / 100 | 0.42 (chain_id=12 idx=2: P0_price=96.11, actual max high=96.53) |

### Root cause

Two interacting bugs in the corrected-detector code paths:

1. **New-high check ran BEFORE invalidation.** A bar with simultaneous
   new high AND deeper low than P0 silently updated `running_max` and
   continued — the deeper low never floated P0 down because the
   invalidation branch was unreachable in that bar's iteration.
2. **Chain-continuation gap unscanned.** The cont walker started at
   `previous_P3 + 1`. Bars in `[previous_P2 + 1, previous_P3]` were
   part of the previous box's breakout phase and never checked. If a
   deeper low than the canonical `cont_p0 = previous_P2_price` existed
   there, the walker missed it entirely.

### Fix (Option A — continuous P0 update)

1. **Swap priority** in `_detect_box_corrected`, `_walk_first_box`, and
   `_walk_chain_continuation`: invalidation FIRST, new-high SECOND.
   When a bar has both, the deeper low respawns P0 at that bar; the
   bar's new high becomes the new `running_max` via the respawn (no
   information lost).
2. **Pre-scan the gap** in `_walk_chain_continuation`: before starting
   the forward walk, iterate `[cont_p0_idx + 1, start_bar)` and float
   `cont_p0` down to the deepest low (or up to the highest high for
   SHORT cont) seen there. The cont's P0 is then guaranteed to be the
   lowest low in the entire [P0, P1] window.

Legacy detector unchanged (it uses `find_peaks` for P1 and prominence-
vetted seeds — immune to both mechanisms).

### Regression tests (2 new, 22/22 total pass)

- `test_bug3_p0_floats_to_deepest_low_when_wide_range_bar_pierces` —
  fixture with a single wide-range bar that has both a new high and a
  low below P0. Pre-H30e the box locks at the shallow seed; post-H30e
  P0 floats to the wide bar.
- `test_bug3_chain_continuation_gap_scan_catches_deeper_low_between_p2_and_p3`
  — asserts the invariant `min(low in [P0..P1]) >= P0_price` (LONG)
  and the mirror for SHORT on the 3-box chain fixture.

### Verification on real DXY data

| Metric | H30d | H30e |
|---|---:|---:|
| Total chained boxes | 265 | 253 |
| LONG violators (deeper low in [P0..P1]) | 69 / 165 | **0 / 135** |
| SHORT violators (higher high in [P0..P1]) | 34 / 100 | **0 / 118** |
| Total violators | 103 / 265 (39%) | **0 / 253 (0%) ✓** |

### Backtest impact

**H30b standalone Variant A:**

| Sym | H30d | **H30e** | Δ |
|---|---:|---:|---:|
| DXY    | −0.61 / 40 | **−0.50 / 37** | +0.11 |
| EURUSD | −0.17 / 25 | **−0.19 / 23** | −0.02 |
| GBPUSD | +1.24 / 24 SWEEP | **+1.29 / 25** SWEEP | +0.05 |
| USDJPY | −0.15 / 29 | **−0.13 / 27** | +0.02 |
| USDCAD | −0.29 / 26 | **−0.51 / 27** | −0.22 |
| AUDUSD | −0.30 / 20 | **−0.33 / 19** | −0.03 |
| NZDUSD | −0.97 / 23 | **−0.88 / 21** | +0.09 |

Modest shifts on most pairs; GBPUSD A holds SWEEP at +1.29.

**H30c chain-conditional Variant A:**

| Sym | H30b H30e | N≥1 OOS | N≥2 OOS | N≥3 OOS |
|---|---|---:|---:|---:|
| DXY    | −0.50 / 37 | −0.21 / 33 | −0.59 / 18 | −0.61 / 10 |
| EURUSD | −0.19 / 23 | +0.19 / 31 | −0.72 / 16 | −1.15 / 9 |
| **GBPUSD** | +1.29 / 25 SWEEP | +0.90 / 22 | **+1.90 / 12 SWEEP** | +0.35 / 6 |
| USDJPY | −0.13 / 27 | +0.78 / 19 | +0.23 / 8 | +0.05 / 3 |
| USDCAD | −0.51 / 27 | −0.66 / 24 | −1.06 / 13 | −0.82 / 6 |
| AUDUSD | −0.33 / 19 | +0.23 / 27 | +0.81 / 15 | +0.79 / 4 |
| NZDUSD | −0.88 / 21 | −0.32 / 20 | −0.31 / 15 | +0.09 / 8 |

**GBPUSD N≥2 surfaces +1.90 / 12 SWEEP** under the corrected detector
— the only cross-floor cell across the (pair × lens) matrix. Still
below the +3.0 GO Sortino floor and the 30-OOS-trade GO trade floor,
so SWEEP not GO. DXY chain context stays negative (consistent with
H30d's invalidation of the H30c +3.34 headline).

**Cell verdict matrix:** 0 GO, 2 SWEEP (GBPUSD standalone A at +1.29,
GBPUSD chain N≥2 at +1.90). Same pair, same direction; consistent
weak-positive signal that doesn't reach a tradeable bar.

### Pattern across the H30 series

The sequence H30a → b → c → d → e is the clearest demonstration in the
program of why visual review of detector output matters. Each catch:

| Rev | Bug | Eliminated artifact |
|---|---|---|
| H30b | `find_peaks` P1 vs running-max | 2008-style "wrong dominant peak" boxes |
| H30c | (chain extension, not a bug) | n/a |
| H30d | P1 collapsed to P0 (1-bar swing) | 132 micro-boxes |
| H30d | P3 marker plotted at wrong y | 397 mis-rendered P3 levels |
| **H30e** | P0 not at deepest low | **103 wrong-P0 boxes** |

Cumulative effect: the H30c "DXY N≥2 +3.34 SWEEP" claim collapses to
−0.59 NO-GO under H30e. **The strongest cross-pair effect is now
GBPUSD's persistent +1.0–1.9 Sortino range across both standalone and
chain-N≥2 lenses** — still NO-GO/SWEEP, but the only signal that
survives all five detector corrections.

### Visuals re-rendered with H30e detector

All 5 PNGs regenerated and re-copied to `~/Documents/4xForecaster/`:
- `figures/26_box_examples_dxy.png` — recent-5 panels show boxes whose
  P0 sits at the deepest low in each window. No remaining "shallow P0"
  cases.
- `figures/27_box_history_dxy.png` — 253 boxes (was 265). Visibly
  cleaner geometry.
- `figures/28/29/30_box_*_examples_5tf.png` — multi-timeframe panels
  refreshed; M5 stays empty (still too thin / narrow window).

### Honest verdict at H30e

After five rounds of bug catches and corrections triggered by Dr. A's
visual review:
- The box-pattern detector is structurally clean (0 micro-boxes, 0
  P0-not-deepest-low cases, P3 markers correct, P1 = running max past
  the first local peak, mega-boxes capped, find_peaks legacy
  reproducible).
- The box-pattern single-box and chain-conditional **trade strategies
  are decisively NO-GO** on every pair at every lens. 0 GO, 2 SWEEPs
  (both GBPUSD; A standalone at +1.29 and chain N≥2 at +1.90).
- The strongest positive Sortino anywhere in the entire arc is GBPUSD
  chain N≥2 at +1.90 — well below the +3.0 GO floor and on only 12
  OOS trades (< 30 GO trade floor).
- Detector substrate quality is now genuinely high; trade-strategy
  edge is genuinely absent. **H31 regime-classifier remains the
  recommended direction** — the box detector's structural strength is
  in providing clean chain/translation signals to aggregate, not in
  generating per-box trade triggers.

## Sources

Visual confirmation (regenerated):
- 5 most-recent DXY boxes with corrected T-mid + variant labels —
  [figures/26_box_examples_dxy.png](../figures/26_box_examples_dxy.png)
- Full DXY history with all 330 detected boxes (170 long / 160 short)
  marked by translation verdict —
  [figures/27_box_history_dxy.png](../figures/27_box_history_dxy.png)

Both also copied to `~/Documents/4xForecaster/` for easy access.

## Visual examples across 5 timeframes (2026-06-20)

Three composite figures, 5 panels each (M5 · M15 · H1 · H4 · Daily),
DXY, generated by [`scripts/h30_visual_examples_5tf.py`](../scripts/h30_visual_examples_5tf.py).
Every panel shows: all 4 points (P0/P1/P2/P3) with distinct colors and
role labels, box shading P0→P3 × P0→P1, height bracket on the left
edge, Variant A's two targets (T1=1.618× and T2=2.236× height, anchored
on P2 and projected from P2 in the breakout direction), the corrected
T1/2 vertical at (P0+P2)/2, an asymmetry annotation, and a date-stamped
title.

- **Bullish-aligned** examples (LONG box + bullish translation +
  P3 confirms above P1):
  [figures/28_box_bullish_examples_5tf.png](../figures/28_box_bullish_examples_5tf.png)
- **Bearish-aligned** examples (SHORT box + bearish translation +
  P3 confirms below P1):
  [figures/29_box_bearish_examples_5tf.png](../figures/29_box_bearish_examples_5tf.png)
- **Failure** examples — definition per spec autonomy rule: detected
  boxes where direction and translation **disagree** (LONG box +
  bearish-translation, or SHORT box + bullish-translation) — what the
  H30 strict confirmation gate filters out as countertrend:
  [figures/30_box_failure_examples_5tf.png](../figures/30_box_failure_examples_5tf.png)

Each panel uses the existing `box_pattern.detect_boxes_df` (corrected
defaults `t_endpoint='p2'`, `max_length=250`). Selection criterion:
clearest geometry (|P1 − T1/2| ≥ 3 bars, box length 20–100 bars, height
≥ 0.5% of price); if no box meets the strict criteria, the criteria
relax to length 10–150 before a panel is marked "no clean example
available." Recency is secondary to clarity.

**Category × timeframe matrix (clean = a panel is filled; "no example"
= the panel carries an annotation explaining the absence):**

| Timeframe | Bullish | Bearish | Failure |
|---|---|---|---|
| M5    | no example | no example | no example |
| M15   | no example | no example | clean      |
| H1    | clean      | clean      | clean      |
| H4    | clean      | clean      | clean      |
| Daily | clean      | clean      | clean      |

The M5 absence is the expected outcome of the 104-day Jan→May 2026 M5
window combined with the 0.5%-of-price height floor (DXY moved in a
narrow range over that window, and the boxes that *do* form are mostly
below the noise floor). M15 keeps the failure panel but loses the
aligned ones for the same reason on a more selective height filter.
H1, H4 and Daily all yield clean examples in every category.

All three PNGs are also copied to `~/Documents/4xForecaster/` so Dr.
A can open them directly.
