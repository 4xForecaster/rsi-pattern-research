# H31 — Box-translation aggregation as a drop-in for FLD bias (2026-06-21)

> Pre-registered application from [BOX_PATTERN_APPLICATIONS.md](../docs/BOX_PATTERN_APPLICATIONS.md) §2.
> Built on the H30f-corrected box detector (six rounds of visual-review
> bug fixes by Dr. A; structurally clean substrate).

## TL;DR — PASS_WITH_MIGRATION (3/7 GO at strict, +USDJPY, −GBPUSD/NZDUSD)

| Source | OOS Sortino GOs (pre-H24) | GO set | Net vs FLD |
|---|---:|---|---|
| FLD baseline (10,20,40)             | **4** | EURUSD, GBPUSD, USDCAD, NZDUSD | reference |
| Box-regime strict (5/5 unanimous)   | **3** | EURUSD, USDCAD, **USDJPY**     | floor cleared; +USDJPY, −GBPUSD, −NZDUSD |
| Box-regime relaxed (≥4/5 majority)  | **1** | USDJPY                          | FAIL the floor |

Box-regime strict clears the literal ≥3-of-7 pre-registered pass floor.
It also ADDS USDJPY (a pair FLD-bias couldn't reach). But it loses two
prior FLD GOs (GBPUSD, NZDUSD). Net GO count drops 4 → 3 — the floor
holds, but the substitution *migrates* which pairs qualify rather than
universally strengthening the list. Relaxed (≥4/5) over-fires the
bullish bucket and fails the floor outright (1 GO).

**H24 robustness gate** — none of the GO cells reach SOLID_GO (4/4):
- FLD GOs through H24: EURUSD DOWNGRADE (0/4), **GBPUSD THIN_GO (2/4)**, USDCAD DOWNGRADE (0/4), NZDUSD DOWNGRADE (0/4) → 1 survivor
- Strict box GOs through H24: **EURUSD THIN_GO (2/4)**, USDCAD DOWNGRADE (1/4), USDJPY DOWNGRADE (1/4) → 1 survivor
- Relaxed box GOs through H24: **USDJPY THIN_GO (2/4)** → 1 survivor

Per-pair H24-survivor count is **tied at 1 across all three regime
sources** — but the surviving pair is different under each (GBPUSD /
EURUSD / USDJPY respectively). No promotion to live trading is
warranted today; the M-P1 strategy module gains a `regime_source` flag
so per-symbol promotion remains possible under explicit operator
approval + per-symbol H24 SOLID_GO.

## What it is

The 4-point box detector tags every confirmed pattern with an
**asymmetry** field:

- `bullish` — P1 (the peak/trough) is *right of T-mid = (P0+P2)/2*,
  meaning the rally/decline portion took longer than the correction
  (Hurst's third law: right-translation = longer-component dominance)
- `bearish` — P1 left of T-mid; rally was fast, correction slow
  (countertrend)
- `neutral` — P1 ≈ T-mid

The asymmetry is the *box's* underlying-pressure tag, independent of
the box's LONG/SHORT direction. A SHORT box can have bullish
asymmetry (the decline portion lengthened more than the recovery,
which is itself a bullish *underlying* read in Hurst's framing — the
longer component dominates).

**Aggregation rule.** Look at the last N boxes whose P3 is confirmed
at or before the bar of interest. Count `bullish` vs `bearish`:
- **strict**  — N bullish → `bullish_regime`; N bearish → `bearish_regime`; else `neutral_regime`
- **relaxed** — ≥(N−1) bullish AND majority bullish → `bullish_regime`; mirror for bearish; else `neutral_regime`
- `unknown` — fewer than N completed boxes yet

The label feeds Scheme D's bullish/neutral/bearish multipliers exactly
where FLD-bias did. The brief mandates the same strict/relaxed rules
across all pairs — no per-pair threshold tuning.

## Implementation

New public API in `src/rsi_pattern/box_pattern.py`:

```python
def box_regime_label(boxes, asof_idx, *, window_n=5,
                      threshold='strict') -> RegimeLabel: ...
def box_regime_series(df, *, window_n=5, threshold='strict',
                       chain_mode=True, boxes=None, ...) -> pd.Series: ...
```

The series form detects once and steps an O(n) cursor; the singleton
form is a pure read of a pre-detected `boxes` list. Both treat
P3-completion as the causality boundary — a box only contributes once
its P3 bar has passed.

Backtest harness: `scripts/h31_box_regime_classifier.py`. Mirrors the
H23 7-pair pipeline (identical loose-M PatternConfig dip=50, identical
70/30 chronological split, identical Scheme D 0×/1×/3× sizing,
identical OOS-Sortino + full-trade-count GO rules), with the regime
source swappable across three variants:

| Variant       | Source                                          |
|---|---|
| `fld`         | `fld.fld_bias(df, cycles=(10,20,40))['bias_label']` (H23 reference) |
| `box_strict`  | `box_regime_series(df, window_n=5, threshold='strict')`             |
| `box_relaxed` | `box_regime_series(df, window_n=5, threshold='relaxed')`            |

Box detection is restricted to the slice being scored (IS-only when
scoring IS; OOS-only when scoring OOS) so the regime label has no
future leak across the 70/30 boundary.

## Per-pair results

OOS Sortino / OOS trades / decision per variant (sorted by FLD baseline):

| Pair    | FLD baseline       | Box strict (5/5)   | Box relaxed (≥4/5) |
|---|---|---|---|
| **EURUSD** | **+4.06** / 12 GO  | **+3.25** / 23 GO  | +2.57 /  7 SWEEP   |
| **GBPUSD** | **+5.57** /  9 GO  | +0.65 / 12 NO-GO   | +0.16 /  6 NO-GO   |
| **NZDUSD** | **+5.34** /  4 GO  | −0.20 / 10 NO-GO   | −0.43 /  7 NO-GO   |
| **USDCAD** | **+3.12** / 15 GO  | **+3.12** / 18 GO  | +1.17 / 13 SWEEP   |
| AUDUSD  | +1.85 /  9 SWEEP   | +1.02 / 18 SWEEP   | +0.99 / 14 NO-GO   |
| **USDJPY** | +1.64 / 16 SWEEP   | **+5.03** / 32 GO  | **+5.24** / 26 GO  |
| DXY     | +1.34 / 19 SWEEP   | +1.14 / 32 SWEEP   | +0.91 / 18 NO-GO   |

Bolded values are GOs.

### Where the migration comes from

- **USDJPY** picks up huge strict GO (+5.03 / 32) because the box-
  translation regime correctly identifies the persistent USD-up trend
  as a sequence of bullish-translation boxes — the strict 5/5 unanimous
  rule rarely fires bullish_regime in this configuration, so the 0×
  bullish multiplier doesn't dominate, and the 3× bearish boost fires
  at the right moments. FLD's bias label is jumpier on USDJPY's noisy
  daily moves around 100/110/130 round numbers; box-translation
  smooths across them.

- **GBPUSD** collapses (+5.57 → +0.65) because the FLD GO was already
  H24-thin (GBPUSD's positive Sortino concentrated in 2024 — see H24
  writeup). The box-translation regime over-classifies GBPUSD as
  bullish_regime through 2019–2023 (recent boxes had bullish
  asymmetry while price meandered), pushing more of those years into
  the 0× bucket. The single-trade 2024-Q1 boost that carried the FLD
  GO doesn't survive the regime relabel.

- **NZDUSD** collapses (+5.34 → −0.20) for the most extreme version of
  the same reason: NZDUSD's FLD GO had already failed H24 (0/4
  conditions) and was carried entirely by ONE +17.4R trade in
  2024-05-01 (Gini 0.93, 100% of profit in a 30-day window). Box-
  translation doesn't reproduce the regime label that admitted that
  trade. Both reads agree that NZDUSD doesn't have a real edge.

- **USDCAD** holds OOS Sortino +3.12 on both FLD and box-strict (the
  trade-count actually rises: 15 → 18). This is the strongest
  consistency across the two regime sources.

- **EURUSD** drops slightly (+4.06 → +3.25) but stays GO and gains
  trade count (12 → 23), and is the only pair to pass H24 THIN_GO
  under box-strict.

### H24 robustness detail

H24 4-test gate (bootstrap p5 ≥ +3.0 / ≥3 of 4 rolling-windows ≥ +3.0 /
Gini ≤ 0.7 / per-trade min Sortino ≥ +2.5) applied to every GO cell:

| Variant       | Pair    | Decision | H24 verdict      | n_hold |
|---|---|---|---|---:|
| fld           | EURUSD  | GO       | DOWNGRADE_SWEEP  | 0/4 |
| fld           | GBPUSD  | GO       | THIN_GO          | 2/4 |
| fld           | NZDUSD  | GO       | DOWNGRADE_SWEEP  | 0/4 |
| fld           | USDCAD  | GO       | DOWNGRADE_SWEEP  | 0/4 |
| box_strict    | EURUSD  | GO       | **THIN_GO**      | 2/4 |
| box_strict    | USDCAD  | GO       | DOWNGRADE_SWEEP  | 1/4 |
| box_strict    | USDJPY  | GO       | DOWNGRADE_SWEEP  | 1/4 |
| box_relaxed   | USDJPY  | GO       | THIN_GO          | 2/4 |

Bootstrap N=10000 seed=42. Rolling windows = 4 × 50%-OOS-span. Gini on
per-trade contribution. Per-trade sensitivity = drop-one rebuild.

## Pre-registered pass-criterion verdict

| Criterion                                                              | Met? | Detail |
|---|:---:|---|
| **PASS** — box-regime variant clears GO on ≥3 of 7 majors              | ✓    | strict has 3 GO |
| **STRONG_PASS** — box-regime ADDS pairs to the GO list FLD couldn't reach | ✓ (USDJPY) | but loses GBPUSD/NZDUSD; net GO drops 4 → 3 |
| **FAIL** — can't match baseline → kill the line                        | ✗    | floor holds |

Calling this **PASS_WITH_MIGRATION**: the literal pre-registered floor
is cleared (3 ≥ 3) AND the substitution adds a pair FLD couldn't
reach, but the net GO count is below baseline. The regime-source swap
is *not* a wholesale upgrade; it's a *different* selectivity profile.

## Production integration

Implemented in `hurst-agent` (separate commit). The integration is
**staged behind a config flag, NOT enabled live**, per the brief's
"don't actually enable for live trade" rule and operator-approval
gating in `CLAUDE.md`:

`hurst-agent/config/rsi_m_p1.yaml`:
```yaml
daily_layer:
  ...
  regime_source: fld                   # fld | box_translation
  box_translation_window_n: 5
  box_translation_threshold: strict    # strict (5/5) | relaxed (>=4/5)
```

`hurst-agent/src/hurst_agent/strategies/rsi_m_p1.py` —
`compute_daily_regime` now branches on `regime_source`. The
`box_translation` branch lazily imports `rsi_pattern.box_pattern`
(requires bumping the `pyproject.toml` pin to a release ≥ H31; the
current `v0.2.0` pin predates the module). 3 new tests added to
`tests/test_rsi_m_p1.py` (regime_source default = fld, box_translation
invokes box_pattern via aux diagnostic, invalid value raises).

**DXY's live cron is untouched.** Default is `regime_source: fld`,
which preserves v0.1 behaviour bit-for-bit.

## Files

- `src/rsi_pattern/box_pattern.py` — `RegimeLabel`, `RegimeThreshold`,
  `_completed_boxes_asof`, `_apply_regime_threshold`,
  `box_regime_label`, `box_regime_series`
- `tests/test_box_pattern.py` — 5 new H31 regression tests
- `scripts/h31_box_regime_classifier.py` — 3-variant 7-pair backtest
  with inline H24 robustness on any GO cell
- `results/_h31_run.json` — full per-symbol JSON dump
- `figures/32_box_regime_vs_fld_sortinos.png` — grouped bar chart
  per pair × variant
- `figures/33_box_regime_label_timeline.png` — DXY 4-panel
  (close + FLD label + strict label + relaxed label) with M-P1
  entries overlaid on the price panel
- `hurst-agent/config/rsi_m_p1.yaml` — `regime_source` switch added
  (default `fld`; DXY unaffected)
- `hurst-agent/src/hurst_agent/strategies/rsi_m_p1.py` — switch wired
  in `compute_daily_regime`
- `hurst-agent/tests/test_rsi_m_p1.py` — 3 H31 regression tests added

## Decision

- Default M-P1 regime source stays **FLD** for every symbol currently
  in the config. No live trade-flow change.
- Box-translation regime is shipped as an option, gated behind the
  per-symbol `regime_source` flag. Promotion of any specific pair to
  `box_translation` requires (a) per-symbol H31 backtest reproducing
  GO, (b) per-symbol H24 SOLID_GO at the chosen threshold, (c) Dr. A's
  explicit approval.
- The detector substrate (H30f-corrected) is now demonstrably useful
  beyond per-box trade triggers — the translation-aggregation regime
  is a genuine cross-scale signal that captures something FLD-bias
  doesn't (USDJPY). H31 confirms the recommended application qualified;
  it does not — yet — confirm it as a strict upgrade.
- The pre-registered criterion in `BOX_PATTERN_APPLICATIONS.md` is
  updated with the PASS_WITH_MIGRATION outcome.
