# Box Pattern — Concrete Applications, Ranked by Leverage

**Date:** 2026-06-18
**Companion to:** [`HURST_TRANSLATION_RULE.md`](HURST_TRANSLATION_RULE.md),
[`results/H29_box_pattern_validation.md`](../results/H29_box_pattern_validation.md)

## What we know after H29 + the Hurst-canon search

- The **detector works** — clean structure detection on FX daily,
  5/5 unit tests, 5/5 DXY mechanics audit, 101 boxes on DXY (34 long
  / 67 short) across 1990–2026.
- The **bias rule's sign is correct** — H29 implemented Hurst's
  canonical translation direction (right ⇒ bullish), confirmed
  across three independent reputable sources.
- The **single-box trade trigger fails** on FX daily — 0/7 GO, median
  OOS Sortino ≈ −0.5. Aligned boxes are ~10–18% of detected boxes;
  their forward returns do not predict trend continuation at the
  locked thresholds.
- The **canonical rule is cross-scale** — Sigma-L (Hickson tradition):
  translation is "evidence of pressure being exerted by **longer
  components**." Single-scale swing boxes don't carry that
  cross-scale context.
- **Box ⊥ M-P1** — 0% same-day overlap on every symbol. Mechanically
  independent signals.

That set of facts is the prior for what's likely to work next.

## Five applications

### 1. Support / resistance zone definition
> The box's P0 (floor) and P1 (ceiling) define a tradeable
> historical range. Subsequent bounces off these levels could be
> intraday entry triggers, and clean breaks could mark trend
> initiations.

**What it does.** Treat completed boxes as persistent S/R zones:
P0 = future support, P1 = future resistance, both valid until
re-tested + broken. Wired as an *intraday* overlay: when 5m price
returns to a daily-box P0 or P1, treat it as a high-quality test.

**Why it might work.** Leverages the detector's strength (clean
structure detection) and avoids its weakness (the failed bias
filter). Doesn't depend on Hurst translation at all — it depends
only on the box endpoints being meaningful chart levels, which the
visual confirmation in `figures/26_box_examples_dxy.png` directly
supports.

**Measurement.** For each completed box on daily, count subsequent
5m bars where price re-touches P0 or P1 (±0.05% tolerance) and
record the forward 1-bar / 10-bar / 60-bar mean and Sortino. Compare
against random level touches. **Success criterion:** mean R after
P0/P1 touch ≥ +0.3 with binomial p < 0.05.

**Leverage:** moderate (orthogonal use of structure; doesn't fix the
M-P1 stack). **Feasibility:** high (no model change; passive
overlay).

### 2. Regime classifier via translation aggregation **[RECOMMENDED]**
> Rolling window of the N most-recent boxes (any direction). If
> ≥70% are right-translated → regime = bullish; if ≥70% are
> left-translated → bearish; else neutral. Could replace or augment
> the simplified FLD bias currently used in Scheme D.

**What it does.** Compute the translation verdict per box (using the
existing `box_pattern.detect_boxes_df`). Maintain a rolling window
(e.g., last 5 or last 10 completed boxes). The dominant translation
becomes the **regime label**: `box_regime ∈ {bullish, bearish, neutral}`.
This becomes a new input to the M-P1 daily Scheme D layer alongside
(or replacing) the FLD bias.

**Why it should work.** This is the cleanest match between detector
strength and the Hurst canon. Sigma-L explicitly frames translation
as evidence of **longer-component pressure** — exactly the kind of
signal you read by *aggregating across boxes*, not by trading any
single one. H29's negative result for single-box trading **predicts**
this version will fare better, because the failure mode (per-box
noise) averages out across the rolling window. Mechanically it also
addresses the cross-scale problem flagged in
`HURST_TRANSLATION_RULE.md`.

**Measurement.** (a) Compute the rolling regime label series for
each symbol. (b) Compute forward 20-bar log-return per bar and
condition on label: report mean/Sortino per label state, plus a
Kruskal-Wallis test for label-vs-return separation. (c) Drop-in
replace the FLD bias in `compute_daily_regime` with the box regime
and re-run the H23 cross-symbol M-P1 backtest. **Pass criterion:**
the box-regime variant clears GO on ≥3 of 7 majors (matching or
beating H23's FLD-bias variant which cleared 3 solid GO).

**Leverage:** highest (touches the *core* M-P1 production stack +
uses Hurst canon at its native scale). **Feasibility:** high (one
function change in the harness; no model retraining; reuses the
existing detector). **This is the H31 recommendation.**

### 3. M-P1 confluence multiplier (lagged, not same-day)
> When an M-P1 LONG fires AND the *most-recent completed box* was
> right-translated, multiply Scheme G's bear multiplier (5×) by
> 1.5×. When the most-recent box was left-translated, multiply by
> 0.5×.

**What it does.** Lag-confluence — the M-P1 signal is the trigger;
the prior box's translation modulates size. Importantly this is
**not** the same-day confluence H29 showed was structurally
impossible (0% overlap). The most-recent completed box is always
some bars stale.

**Why it might work.** If translation does carry directional bias
(per Hurst canon) but at a slower cadence than M-P1's daily M-tops,
this is the right shape for combining them. Risks: (a) the bias is
weak (H29 hinted at this), so the multiplier won't move the needle
much; (b) double-counting if the FLD bias and the box translation
are correlated.

**Measurement.** Reuse the H23 OOS pipeline. Compute Sortino with
and without the multiplier override, per symbol. **Pass criterion:**
the modified Scheme G clears GO on ≥1 additional symbol vs.
baseline, with OOS MaxDD not deeper than 1.2× baseline.

**Leverage:** moderate (incremental optimization of a working
strategy). **Feasibility:** high.

### 4. Position-management exit overlay
> While an M-P1 LONG is open, watch for a *new* completed box. A
> left-translated box (or any SHORT box) forming during the held
> long is an early-exit signal — close at the next bar's open
> regardless of T1/T2/T3.

**What it does.** Risk management overlay, not a new entry strategy.
Translation is used as a *deterioration* signal rather than an entry
predictor.

**Why it might work.** The H29 result that aligned LONG boxes don't
produce edge cuts *both* ways — left-translated boxes appearing in
an open position may genuinely signal that the cross-scale pressure
turned bearish, even if the entry signal failed. The position is
already at risk; this is asymmetric (only ever cuts gains short
*early*, never adds size).

**Measurement.** Compare R-multiple distribution of M-P1 LONGs
*with* vs *without* the exit overlay. **Pass criterion:** mean R
improves AND tail loss does not worsen.

**Leverage:** moderate (purely defensive; cannot create alpha,
only preserves it). **Feasibility:** high (overlay on existing
simulation engine).

### 5. Time-cycle harmonic filter
> Filter trades to only those whose box length (P0 → P3) matches the
> canonical 10/20/40 daily harmonic bands (±25%).

**What it does.** Sharpens the H29 single-box trade strategy by
restricting to dominant-cycle boxes. Combined with the visual
finding that the detector can produce 1000-bar "mega-boxes" (the
2022–2026 SHORT box on DXY in fig 26), a length filter is also a
sanity bound.

**Why it might work.** Hurst's translation rule is for dominant
cycles. The H29 detector is scale-agnostic — many of its boxes are
subordinate harmonics where translation doesn't predict trend. A
length filter is the most direct way to restrict to the rule's
intended scale.

**Measurement.** Re-run the H29 backtest with length ∈ {8–12,
16–24, 32–48} as three separate strategies. **Pass criterion:** at
least one band clears GO on ≥1 symbol while keeping ≥10 OOS trades.

**Leverage:** low (sharpens a strategy that already failed; even if
it works, the win would be a marginal one). **Feasibility:** high.

## Ranking and recommendation

| # | Application | Leverage | Feasibility | Hurst-canonical | Fixes H29 weakness |
|---|---|---|---|---|---|
| **2** | **Regime classifier via translation aggregation** | **highest** | high | **yes** (cross-scale) | **yes** (averages over noise) |
| 3 | M-P1 confluence multiplier (lagged) | moderate | high | partial | partial |
| 4 | Position-management exit overlay | moderate | high | partial | partial (defensive only) |
| 1 | Support/resistance zone definition | moderate | high | no | uses detector strength |
| 5 | Time-cycle harmonic filter | low | high | yes (scale-restricts) | partial (still single-box) |

## Recommended H31

**Implement #2 — Regime Classifier via Translation Aggregation.**

It's the only application that simultaneously (a) leverages the
detector's confirmed strength (clean structure detection),
(b) avoids its confirmed weakness (single-box bias filter failure),
(c) restores the Hurst-canonical *cross-scale* framing the canon
explicitly requires (Sigma-L: "evidence of pressure being exerted by
longer components"), and (d) plugs into the live M-P1 production
stack at a load-bearing seam (FLD bias in `compute_daily_regime`).

The pre-registered H31 test: drop-in replace the FLD-bias term in
`hurst_agent.strategies.rsi_m_p1.compute_daily_regime` with a
rolling-box-translation regime label (window N = last 5 completed
boxes), re-run the H23 7-pair OOS backtest, and require the
box-regime variant to clear GO on ≥3 of 7 majors — i.e., to *at
minimum match* the FLD-bias baseline. Pass that bar and the
detector earns a place in production; miss it and we kill the line.

## H31 result (2026-06-21) — PASS_WITH_MIGRATION

Implementation landed: `box_pattern.box_regime_label` and
`box_pattern.box_regime_series` (asymmetry-aggregation helpers), plus
`scripts/h31_box_regime_classifier.py` (the 7-pair drop-in backtest)
and the hurst-agent integration switch (`daily_layer.regime_source: fld
| box_translation` in `config/rsi_m_p1.yaml`, default `fld`, with the
M-P1 strategy module branching on the flag).

**Pre-registered floor cleared at the strict (5/5) threshold.** Box-
regime strict yields 3 GOs (EURUSD, USDCAD, **USDJPY**), satisfying
the literal ≥3-of-7 PASS criterion. Box-regime ALSO adds **USDJPY** —
a pair FLD-bias couldn't reach — which by the brief's literal
"STRONG_PASS if box-regime ADDS pairs" rule technically qualifies as
STRONG. But the substitution simultaneously *loses* GBPUSD and NZDUSD
(both FLD GOs), so the net GO count drops 4 → 3. The honest verdict
is **PASS_WITH_MIGRATION**: the floor holds, but the regime-source
swap reshuffles *which* pairs qualify rather than universally
strengthening the GO list.

Box-regime relaxed (≥4/5) fails: 1 GO only (USDJPY). The relaxed
threshold over-fires the bullish_regime label and the resulting
contrarian SchemeD 0× drops too many otherwise-positive trades.

**H24 robustness — none reach SOLID_GO** under any variant. EURUSD
strict gets THIN_GO (2/4), USDJPY relaxed gets THIN_GO (2/4), the
rest are DOWNGRADE_SWEEP. By the same H24 bar that filters FLD's GO
list (where only GBPUSD survives as THIN_GO), the box-regime
substitution produces a *different* THIN_GO survivor — EURUSD under
strict — but does not promote any pair past the THIN bar. Per-pair
H24-survivor count is tied at 1 across FLD vs strict vs relaxed.

**Production status.** Per the brief: ≥3 GO triggers the
`regime_source` switch in the M-P1 strategy module. Implemented and
shipped to `hurst-agent` config + strategy + tests. Default is
`regime_source: fld` so DXY's live cron is unchanged. The flag exists
so a per-symbol decision can later promote (e.g.) USDJPY under
`regime_source: box_translation` with explicit operator approval —
but the H24 bar above forbids that promotion today.

**The H31 recommendation in this doc stands, qualified.** The
translation-aggregation regime IS a valid Hurst-canonical cross-scale
signal that earns a place in the M-P1 stack at the regime-source
seam. It is NOT, on this evidence, a wholesale upgrade over FLD-bias;
it is a *different* regime-source whose pair selectivity differs.
The integration switch is the right vehicle: per-symbol regime-source
choice, gated on per-symbol H24 SOLID_GO + operator approval.

Detail: `results/H31_box_regime_classifier.md`.
