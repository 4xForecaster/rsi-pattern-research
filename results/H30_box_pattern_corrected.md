# H30 — Box-Pattern Backtest with Corrected Spec

**Date:** 2026-06-20
**Module:** [`src/rsi_pattern/box_pattern.py`](../src/rsi_pattern/box_pattern.py)
**Tests:** [`tests/test_box_pattern.py`](../tests/test_box_pattern.py) — **8/8 pass**
**Script:** [`scripts/h30_box_pattern_corrected.py`](../scripts/h30_box_pattern_corrected.py)
**Run dump:** [`results/_h30_run.json`](_h30_run.json)
**Figures (regenerated):** [`figures/26_box_examples_dxy.png`](../figures/26_box_examples_dxy.png),
[`figures/27_box_history_dxy.png`](../figures/27_box_history_dxy.png)
**Compare against:** [`results/H29_box_pattern_validation.md`](H29_box_pattern_validation.md) (preserved)

## TL;DR — corrections made, both variants still 0/7 GO (re-confirmed after Variant A tightening)

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

## Sources

Visual confirmation (regenerated):
- 5 most-recent DXY boxes with corrected T-mid + variant labels —
  [figures/26_box_examples_dxy.png](../figures/26_box_examples_dxy.png)
- Full DXY history with all 330 detected boxes (170 long / 160 short)
  marked by translation verdict —
  [figures/27_box_history_dxy.png](../figures/27_box_history_dxy.png)

Both also copied to `~/Documents/4xForecaster/` for easy access.
