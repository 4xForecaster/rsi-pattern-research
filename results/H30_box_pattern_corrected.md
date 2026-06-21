# H30 — Box-Pattern Backtest with Corrected Spec

**Date:** 2026-06-20
**Module:** [`src/rsi_pattern/box_pattern.py`](../src/rsi_pattern/box_pattern.py)
**Tests:** [`tests/test_box_pattern.py`](../tests/test_box_pattern.py) — **8/8 pass**
**Script:** [`scripts/h30_box_pattern_corrected.py`](../scripts/h30_box_pattern_corrected.py)
**Run dump:** [`results/_h30_run.json`](_h30_run.json)
**Figures (regenerated):** [`figures/26_box_examples_dxy.png`](../figures/26_box_examples_dxy.png),
[`figures/27_box_history_dxy.png`](../figures/27_box_history_dxy.png)
**Compare against:** [`results/H29_box_pattern_validation.md`](H29_box_pattern_validation.md) (preserved)

## TL;DR — corrections made, both variants still 0/7 GO

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
- **Variant A** (primary): `1.618 / 2.345 / 3.456 × box.height`, anchored
  on P2.
- **Variant B** (alternative): `1.618 / 2.236 / 3.618 × box.height`,
  anchored on P1.

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

| Symbol | H29 OOS Sortino / n | H30 A OOS / n | H30 B OOS / n | Decision A / B |
|---|---|---|---|---|
| DXY    | −0.46 /  3 | **−0.78 / 29** | **−0.89 / 31** | NO-GO / NO-GO |
| EURUSD |   n/a  /  0 | **−1.42 / 29** | **−1.20 / 32** | NO-GO / NO-GO |
| GBPUSD | −1.21 /  2 | **−0.70 / 18** | **−0.56 / 18** | NO-GO / NO-GO |
| USDJPY | −0.76 /  2 | **−0.40 / 28** | **−0.39 / 30** | NO-GO / NO-GO |
| USDCAD | +0.43 /  4 | **−0.17 / 19** | **−0.12 / 21** | NO-GO / NO-GO |
| AUDUSD | −0.19 /  6 | **+0.32 / 32** | **+0.70 / 32** | NO-GO / NO-GO |
| NZDUSD | −1.65 /  6 | **−0.12 / 28** | **+0.10 / 29** | NO-GO / NO-GO |

H24 robustness gate not invoked anywhere — no pair cleared the GO
prerequisite.

Variant ranking on OOS Sortino across pairs (a tie-breaker for any
future H31 use of either target ladder): **Variant B slightly edges
Variant A on 6 of 7 pairs**. The interpretation is structural —
Variant B anchors targets on P1 (higher than P2) so targets sit
further from entry; when trades work they capture more right tail. It
is not, however, enough right tail to flip any pair to a tradeable
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

## Sources

Visual confirmation (regenerated):
- 5 most-recent DXY boxes with corrected T-mid + variant labels —
  [figures/26_box_examples_dxy.png](../figures/26_box_examples_dxy.png)
- Full DXY history with all 330 detected boxes (170 long / 160 short)
  marked by translation verdict —
  [figures/27_box_history_dxy.png](../figures/27_box_history_dxy.png)

Both also copied to `~/Documents/4xForecaster/` for easy access.
