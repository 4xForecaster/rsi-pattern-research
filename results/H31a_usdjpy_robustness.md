# H31a — USDJPY box-strict regime: H24 robustness pass + visual proof (2026-06-21)

> Built on H31 (commit [4ba3fd4](https://github.com/4xForecaster/rsi-pattern-research/commit/4ba3fd4))
> and the H30f-corrected detector substrate.

## TL;DR — DOWNGRADE_SWEEP (1/4 conditions hold), edge concentrated 2021-Q1 → 2022-Q1

USDJPY under H31 `box_strict` was the first cell in the box-pattern arc to
clear BOTH the +3.0 Sortino floor (+5.03 OOS) AND the 30-trade floor
(32 OOS trades). H31's inline H24 reported DOWNGRADE (1/4). This standalone
re-run with explicit numbers **reproduces that verdict exactly**.

| H24 test | Threshold | Number | Verdict |
|---|---|---:|---:|
| [1] Bootstrap p5 (N=10000 seed=42)        | ≥ +3.0  | **+1.78** (p50 +4.21, p95 +10.30, nan-rate 0%) | **FAIL** |
| [2] Rolling 50%-OOS-span × 4 windows      | ≥ 3/4 ≥ +3.0 | **2/4** (+12.37, nan, +7.47, +1.73) | **FAIL** |
| [3] Gini of trade contribution            | ≤ 0.70  | **0.7396** (profit-only 0.5423; single-30d-share 26%) | **FAIL** |
| [4] Per-trade drop-one min Sortino        | ≥ +2.5  | **+4.49** (worst case: drop 2021-10-01 R=+4.42) | **PASS** |

**1/4 → DOWNGRADE_SWEEP.** The OOS +5.03 Sortino headline is structurally
weak in three of the four lenses: bootstrap tail tells you the central
estimate is unreliable, the rolling timeline tells you the edge is
front-loaded (12.37 → 7.47 → 1.73 across the OOS span), and the Gini
tells you trade contribution is concentrated (just over the 0.7 cap).
Only the per-trade sensitivity test passes — the strategy isn't a
one-trade artifact, but that's a low bar.

The drop-one PASS deserves explicit framing: it shows the result *isn't*
the kind of small-sample mirage NZDUSD had at H23 (where dropping the
single best trade sent Sortino from +5.34 to −0.66). USDJPY box-strict
has real positive evidence — just regime-concentrated and time-concentrated.

## How USDJPY box-strict actually traded

32 OOS trades, 2017-07-17 → 2026-05-18. **Every trade used the 1×
neutral_regime multiplier.** Under the strict 5/5 unanimous rule the
bullish_regime label (which would 0× kill the trade) and bearish_regime
label (which would 3× boost it) almost never fire on USDJPY — meaning
the H31 strict variant on USDJPY is essentially the M-P1 LONG base
strategy without any sizing modification, with one exception: the
earliest OOS trade (2018-04-13) entered with regime=`unknown` (the
first ≤5-box window hadn't yet completed), which falls back to 1×.

That's diagnostic. The "regime substitution" on USDJPY isn't reading a
new directional signal — it's reading "no strong unanimous translation
verdict ever forms in 5-box rolling windows" and letting the base
strategy through at 1×. The +5.03 OOS Sortino is therefore the M-P1
base strategy's OOS Sortino on the 32-trade subset where strict-rule
neutrality holds — which is the entire OOS slice on USDJPY. It is
**not** evidence that the translation-aggregation regime *adds*
information; it's evidence that strict 5/5 unanimity rarely fires on
USDJPY and the unchanged base strategy itself happened to be positive
in the 2021–22 JPY decline window.

## Per-trade ledger (sorted by R)

Top 8 by R (the actually-shipped contribution = R × multiplier
== R × 1.0):

| # | Entry → Exit | Entry → Exit price | R | Regime label | Exit reason |
|---:|---|---|---:|---|---|
| 1 | 2021-10-01 → 2022-03-28 | 111.10 → 122.50 | **+4.42** | neutral_regime | T3 |
| 2 | 2021-01-29 → 2021-06-23 | 104.60 → 110.84 | **+3.96** | neutral_regime | T3 |
| 3 | 2021-09-13 → 2021-10-20 | 109.95 → 113.83 | **+3.83** | neutral_regime | T3 |
| ... | (middle trades) | ... | +0.7 to +1.2 | neutral_regime / unknown (early) | time / partial-targets |
| n−1 | 2024-06-17 → 2024-07-31 | 158.05 → 153.05 | **−1.00** | neutral_regime | initial_stop |
| n   | 2024-12-11 → 2025-04-22 | 152.93 → 148.85 | **−1.00** | neutral_regime | initial_stop |

The three R≥+3.8 trades are all 2021-Q1 → 2022-Q1 — the JPY decline from
~104 to ~130. The two full −1R losers are both late-OOS: 2024-06 and
2024-12 entries that stopped out into BoJ-intervention-era reversals.
Both failures match the structural mismatch the existing `rsi_m_p1.yaml`
notes for USDJPY ("long-only engine vs JPY's durable USD-up trend
regime — long M-top entries fade into trend"). The H31 strict regime
substitution doesn't address that structural mismatch; it just keeps
the trade live because no strong unanimous bullish-translation window
formed to fire the 0× skip.

## Visual proof — does the detector read the structure Dr. A reads?

Figure 35 shows 8 representative OOS USDJPY M-P1 LONG entries (3
biggest winners + 3 around the median + 2 losers — no cherry-pick).
Each panel renders:

- USDJPY candlesticks ± ~100 bars around the entry
- The last 5 completed boxes preceding the entry, color-coded by
  translation verdict (green = bullish-translation, red = bearish-
  translation, gray = neutral)
- Entry marker (blue ▲) and exit marker (blue ▽)
- Title with regime label / multiplier / R / exit reason

**Visual takeaway** — looking at the 5-box history preceding each
entry, USDJPY boxes around M-P1 entries are predominantly
green (bullish-translation: P1 right of T-mid, longer-component
dominance to the upside). That's consistent with USDJPY's
multi-year USD-up trend. Yet strict-5/5 almost never fires
`bullish_regime` because at least one neutral or bearish box
breaks the unanimity in nearly every 5-box window. The 1×-everywhere
behaviour falls out of that.

The detector IS reading the same structure Dr. A would read (upward-
trending box population through the JPY decline) — but the strict
unanimity rule strips that signal of any usable directional content.
A weaker threshold (e.g. ≥3/5) might recover it; but per the brief
"don't tune the box-regime threshold per pair", that exploration
belongs in a follow-up H series, not in H31a.

## Comparison: H31 inline vs H31a explicit

H31's inline H24 in `scripts/h31_box_regime_classifier.py` reported
DOWNGRADE (1/4). H31a's standalone re-run with the same locked
parameters confirms 1/4. The two numbers should match exactly because
the same code path computes them; flagging any divergence here for
auditability:

| Test | H31 inline | H31a standalone |
|---|---:|---:|
| Bootstrap p5 (decision) | not stored | **+1.777** |
| Rolling n ≥ +3.0       | 2/4 | **2/4** |
| Gini                   | 0.7396 | **0.7396** |
| Per-trade min Sortino  | not stored | **+4.488** |
| n_hold                 | 1 | **1** |
| verdict                | DOWNGRADE_SWEEP | **DOWNGRADE_SWEEP** |

H31a adds the per-test numbers H31 inline elided (bootstrap p5,
per-trade min) for completeness; the verdict reproduces exactly.

## Decision — hurst-agent untouched

USDJPY under H31 box-strict **does not clear H24 SOLID_GO** (and does
not clear H24 THIN_GO either; 1/4 < 2/4). Per the brief and per
`docs/BOX_PATTERN_APPLICATIONS.md` § "H31 result": promotion to
`regime_source: box_translation` on USDJPY requires SOLID_GO + Dr. A's
approval. Today, neither holds.

- `hurst-agent/config/rsi_m_p1.yaml` is **NOT modified** by this experiment.
- The H31 staging branch [`h31/regime-source-switch`](https://github.com/4xForecaster/hurst-agent/pull/new/h31/regime-source-switch)
  remains the integration vehicle; it does not enable `box_translation`
  for any symbol.
- DXY's live cron path is untouched (default `regime_source: fld`).

## Files

- [`scripts/h31a_usdjpy_robustness_and_visuals.py`](../scripts/h31a_usdjpy_robustness_and_visuals.py)
- [`results/_h31a_usdjpy_h24.json`](_h31a_usdjpy_h24.json) — full numerical dump
- [`figures/34_usdjpy_h24_robustness.png`](../figures/34_usdjpy_h24_robustness.png)
- [`figures/35_usdjpy_box_translation_examples.png`](../figures/35_usdjpy_box_translation_examples.png)
- Both PNGs also copied to `~/Documents/4xForecaster/`

## What it would take to flip this to SOLID_GO

Just naming the bar so it's explicit:

1. Bootstrap p5 ≥ +3.0 — currently +1.78. Needs a more uniformly-positive
   trade contribution distribution. Not achievable by re-running on the
   same OOS slice; would need either (a) longer OOS history with the
   2024-onward BoJ regime trades better-handled, or (b) a different
   bullish/bearish classification on those 2024 trades that makes the
   0× skip fire.
2. ≥3/4 rolling windows ≥ +3.0 — currently 2/4 (W1 +12.37, W3 +7.47;
   W2 has no trades; W4 +1.73). The W4 weakness is the late-OOS BoJ
   intervention era. Same comment as (1) — structural.
3. Gini contribution ≤ 0.70 — currently 0.7396 (just over). Would
   probably clear after (1) or (2); not the binding constraint.
4. Per-trade min Sortino ≥ +2.5 — already PASS at +4.49.

The two structural issues (1, 2) point at the same root cause: the
2024-onward BoJ regime trades the long-only engine cannot handle. That
is the *exact* failure mode the existing `rsi_m_p1.yaml` notes already
called out: "STRUCTURAL: long-only engine vs JPY's durable USD-up
trend regime — long M-top entries fade into trend. Needs a
regime/trend overlay, NOT a knob sweep and NOT a short-side flip."

H31 box-translation IS the regime overlay that note prescribed.
Strict-5/5 *doesn't fix it*. A relaxed threshold (the brief's
≥4/5 variant) puts more windows into bullish_regime and skips more
trades, which lifted USDJPY further on the OOS surface to +5.24 (26
trades, H24 THIN_GO 2/4). That suggests the relaxed-threshold direction
is where the residual USDJPY signal lives — but, again, by brief rule
("global strict/relaxed rules across all pairs"), per-pair threshold
shopping is out of scope.
