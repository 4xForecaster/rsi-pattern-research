# SYMBOLS_TESTED — running ledger of the daily Scheme D regime layer

Single source of truth for *which symbols have been run through the
DXY-calibrated daily Scheme D framework, what the verdict was, and why*.
Append-only. Newest experiment block at the bottom.

**Framework under test (fixed, never re-tuned per symbol):**
loose-M (`PatternConfig` default, dip=50) → `fld_bias` cycles (10,20,40) →
Scheme D sizing bullish 0× / neutral 1× / bearish 3× → 1% risk/trade,
daily non-overlapping equity. Decision on the **70/30 OOS** protocol:
GO = OOS Sortino ≥ +3.0 AND full trades ≥ 30; NO-GO = OOS Sortino < +1.0
OR full trades < 10; SWEEP otherwise.

M-LONG decision is the daily Scheme D verdict above. **V-SHORT (H25)** is
the symmetric V-floor-breach SHORT decision (same 70/30 protocol, inverted
Scheme D, no re-tune); directional quadrant in the last column.

| Symbol | Class | M-LONG Decision | OOS Sortino | OOS Tr | Full Sortino | Full Tr | Exp. | M-LONG Live? | V-SHORT (H25) | Quadrant |
|---|---|---|---:|---:|---:|---:|---|---|---|---|
| DXY | index | GO (shipped) | +5.38 (7y) / +1.34 (70/30)† | 14 / 19 | +5.75 | 56 | H12/H15 | **yes** (`enabled: true`) | NO-GO (OOS +0.10) | NEITHER |
| USDMXN | fx_emerging | SWEEP | +2.53 | — | +4.41 | 26 | H15/H16 | no | NO-GO (OOS +0.54) | NEITHER |
| USDCHF | fx_major | NO-GO | — | — | +0.87 | 25 | H15 | no | NO-GO (OOS +0.48) | NEITHER |
| EURUSD | fx_major | **GO** | +4.06 | 12 | +3.15 | 30 | H23 | no (`enabled: false`) | SWEEP (GO-by-rule, H24-robust 1/4) | LONG-ONLY |
| USDCAD | fx_major | **GO** | +3.12 | 15 | +4.36 | 35 | H23 | no (`enabled: false`) | NO-GO (OOS +0.38) | LONG-ONLY |
| GBPUSD | fx_major | **THIN GO** (H24 2/4) | +5.57 | 9 | +4.91 | 34 | H23→H24 | no (`enabled: false`) | SWEEP (OOS +2.24) | LONG-ONLY |
| NZDUSD | fx_major | **SWEEP** (H24 0/4, downgraded) | +5.34 | 4 | +4.42 | 35 | H23→H24 | no (`enabled: false`) | NO-GO (OOS −0.26) | LONG-ONLY |
| AUDUSD | fx_major | SWEEP | +1.85 | 9 | +2.21 | 33 | H23 | no | NO-GO (OOS −2.76) | NEITHER |
| USDJPY | fx_major | SWEEP | +1.64 | 16 | +1.34 | 47 | H23 | no | SWEEP (OOS +2.44) | NEITHER |
| USDSEK | fx_exotic | NOT RUN | — | — | — | — | — | no | NOT RUN | — |
| USDZAR | fx_exotic | NOT RUN | — | — | — | — | — | no | NOT RUN | — |
| BTCUSD | crypto | NO-GO (H26/H27) | +0.65 | 5 | +8.30 | 26 | H26→H27 | no | NOT RUN | — |
| ETHUSD | crypto | NO-GO¹ → **FWD-TEST candidate** (H27, RSI9 cadence) | +12.55 (D0) / +6.19 (RSI9) | 7 / 12 | +19.63 | 25 | H26→H27 | no | NOT RUN | — |
| SOLUSD | crypto | NO-GO (H26/H27; RSI7 GO killed by robustness 0/4) | −0.45 / +3.79 (RSI9) | 4 / 12 | +4.11 | 13 | H26→H27 | no | NOT RUN | — |
| BNBUSD / XRPUSD | crypto | NOT RUN (bonus gated on BTC/ETH GO) | — | — | — | — | H26 | no | NOT RUN | — |

† DXY shipped on the H15 full-sample decision and a 7-year OOS window
(+5.38). Under the *stricter* H23 70/30 split DXY itself is only SWEEP
(OOS +1.34) — i.e. the H23 bar is harder than the bar DXY cleared.

## V-SHORT (H25, 2026-05-19) — directional negative result

Symmetric V-floor-breach SHORT tested across all 9 pairs. Faithfulness
gate passed (DXY mean R +0.4766 ≈ H8 +0.48); long/short trailing-stop
symmetry unit-tested 12/12. **Zero V-SHORT GOs.** Quadrant tally: 4
LONG-ONLY, 5 NEITHER, 0 SHORT-ONLY, 0 BOTH. The directional-inverse
hypothesis (M-LONG-fail pairs flip to V-SHORT GO) is **falsified** — the
supposed beneficiaries are the worst V-SHORT performers (AUDUSD OOS
−2.76, USDMXN +0.54, USDCHF +0.48). EURUSD V-SHORT was GO-by-rule (OOS
+4.26 / full 34) but the H24 robustness gate caught it as a cluster
artifact (Gini 0.92, 1/4) and downgraded it — the same mechanism that
caught NZDUSD M-LONG, confirming the gate generalizes across directions.
**No hurst-agent integration** (0 GO ⇒ no `v_short_symbols:` block, no
`v_short.py`, no schema bump). `strategies_vshort.py` kept as a faithful
unit-tested research asset. Detail: results/H25_vshort_expansion.md.

## Crypto (H26, 2026-05-19) — 0 GO, signal-scarcity not edge-failure

¹ Daily M-P1 LONG, DXY params unchanged, on BTC/ETH/SOL (yfinance,
7-day/wk ~365 bars/yr). Data clean as fetched (0 NaN/dup, monotonic, no
>50% single-bar moves; nothing excluded). **0 GO** under the H26 brief's
OOS-trade STRICT rule — and robust to PRAGMATIC too (no crypto major
reaches 30 *full* trades: BTC 26, ETH 25, SOL 13). Key nuance: **ETHUSD
OOS Sortino +12.55 — the highest OOS Sortino in the whole H12–H26
program — but NO-GO purely on the 7<10 OOS-trade floor**, with NO IS→OOS
degradation (IS +31.74, FULL +19.63). The M-P1 *edge* appears to transfer
to crypto (possibly better than to FX); the FX-calibrated **cycle
geometry** does not — BTC 2014-2020 cycle recon shows dominant periods
~5–8 & ~20 bars, the 40-bar parent absent, so loose-M + FLD(10,20,40)
under-samples crypto and never reaches the trade-count floors. No
hurst-agent integration (0 GO). Actionable next step: **H27 — crypto-
native cycle re-recon + ladder (e.g. 5/10/20 or 8/16/32)** as a fresh
calibrated experiment, then re-test at the locked floors. Detail:
results/H26_crypto_expansion.md.

## Crypto cadence recalibration (H27, 2026-05-21)

H26's "recalibrate the FLD ladder" hypothesis is **falsified**: the FLD
ladder is a **null lever** — the M-top universe is invariant to it (BTC
24 / ETH 16 / SOL 7 across (10,20,40)/(5,10,20)/(8,16,32)/(6,12,24)); it
only drives Scheme-D sizing. The **real lever is detection cadence**:
shortening RSI + scaling the M timing windows grows the universe (BTC
24→41, ETH 16→27, SOL 7→19) and preserves the edge. Pre-registered
primary cadence = **RSI9, windows ~0.64×** (theory/recon-chosen, the
*moderate* option — NOT the best-OOS RSI7, anti-cherry-pick). Faithfulness:
RSI14 reproduces H26 exactly.

**Primary-rule (RSI9 / STRICT OOS-trade) result: 0 GO.** Reads:
- **ETHUSD → forward-test candidate.** RSI9 cadence: OOS Sortino +6.19 on
  12 trades, PRAGMATIC GO, robustness THIN (2/4); RSI7: +7.53/16, also
  PRAGMATIC GO 2/4. STRICT still SWEEP (<30 OOS trades) and OOS was peeked
  in exploratory probing → **forward/paper watchlist, NOT live**. Clean
  test = forward data (H28).
- **SOLUSD** — RSI9 SWEEP both rules; RSI7 PRAGMATIC GO is a cluster
  artifact (robustness 0/4) → killed. Not tradeable yet (short history).
- **BTCUSD** — universe grows with cadence but OOS Sortino stays ~+0.7–1.0
  → NO-GO at every cadence; no OOS edge independent of sampling.

No hurst-agent change (0 GO at the primary bar; ETH is a candidate, not a
classification). The cadence lever is now validated program-wide (explains
why low-N symbols fail + how to grow their universe without touching edge
logic). Detail: results/H27_crypto_cycle_recalibration.md.

## TimesFM zero-shot benchmark (H28, 2026-06-18)

Pretrained Google TimesFM 2.5 (200M, PyTorch checkpoint
`google/timesfm-2.5-200m-pytorch`) benchmarked zero-shot on daily DXY,
EURUSD, USDCAD with a 1000-bar context, horizons {1, 5, 20}, same 70/30
OOS slice as the rest of the H-series. Three pre-registered axes; **0/3
cleared on all 3 symbols**:

| Symbol | (a) RMSE-vs-baselines | (b) Directional ≥55%, p<0.05 | (c) Calibration ≤ 5pp dev | TimesFM verdict |
|---|---|---|---|---|
| DXY    | ❌ TimesFM loses all 3 horizons | ❌ acc 0.495–0.502 (p≫0.05) | ❌ 50.8 pp deviation | **negative** |
| EURUSD | ❌ TimesFM loses all 3 horizons | ❌ acc 0.507–0.511 (p≫0.05) | ❌ 50.6 pp deviation | **negative** |
| USDCAD | ❌ TimesFM loses all 3 horizons | ❌ acc 0.501       (p≫0.05) | ❌ 51.4 pp deviation | **negative** |

The calibration failure is the largest: TimesFM's nominal 80%/90% bands
cover only ~29% of realized log-returns — confidently wrong, not just
inaccurate. Random walk + 20-bar trend continuation beat it on every
horizon. No `TIMESFM_INTEGRATION.md` written, hurst-agent untouched.
Negative is specific to **zero-shot daily price-level forecasting on
these 3 FX series** — does not preclude separately benchmarked use cases
(intraday, covariates) which would be their own H-series. Detail:
results/H28_timesfm_negative.md.

## Box detector P1-mis-track fix + nested-box flag (H30f, 2026-06-20) — SWEEPs migrate GBPUSD → EURUSD, still 0 GO

Dr. A's sixth visual catch on the regenerated H30e figures: **(Issue 1)**
the 1993 DXY LONG REV box had P1 at ~91.97 while higher peaks in July/
August 1993 (real max **95.64** at idx 916) sat right there on the
chart — same class of bug as H30b's "P1 must be the dominant swing
high" but surviving five revisions. **(Issue 2)** the detector should
also find smaller sub-boxes that satisfy the full 4-point construction
inside a larger parent's [P0..P3] window, gated behind `nested=True`.

Root cause for Issue 1: `_walk_chain_continuation`'s rev-track state
(running max for the eventual reversal box's P1) was rebuilt fresh on
every walker call AND bars in `(P2_cont, P3_cont]` were never processed
for the rev track — so when a cont box emitted at `j = P2_cont` and the
function returned, bars 890..932 in the 1993 case (including the
95.64-high bar) vanished from rev tracking. Fix: thread `rev_state`
across cont calls, extend the cont-gap pre-scan to also update the
chain-direction running extreme `cont_re`, and add a post-cont-emit
loop that scans `(j, P3_cont]` for the rev track before returning.

Issue 2 fix: new `_add_nested_to_chained` helper. When `nested=True`,
re-runs standalone (non-chained) detection over the same series in
BOTH directions, then assigns each candidate sub-box the smallest
chain parent whose `[P0..P3]` strictly contains it. New `BoxPattern`
fields: `box_id` (monotonic per chain detection) and `parent_box_id`
(None for primaries, set for nested).

Verification — DXY daily: pre-fix had 14/135 LONG + 4/130 SHORT chain
boxes violating `p1_price == extremum(high or low) over [p0_idx..p2_idx]`;
post-fix: **0/266 violators**. Chain 11/0 REV now has P1 at idx 916
= 95.64 (matches Dr. A's expected dominant peak exactly).

Backtest — Variant A chain-conditional under H30f detector:

| Sym | H30b H30f | N≥1 OOS | N≥2 OOS | N≥3 OOS |
|---|---|---:|---:|---:|
| DXY    | −0.50 / 37 | +0.01 / 30 | −0.23 / 16 | −0.12 / 9 |
| **EURUSD** | −0.19 / 23 | **+2.05 / 18 SWEEP** | **+1.19 / 10 SWEEP** | −0.11 / 3 |
| GBPUSD | +1.29 / 25 SWEEP | −0.08 / 20 | +0.39 / 10 | +0.34 / 5 |
| USDJPY | −0.13 / 27 | +0.14 / 13 | −0.22 / 3 | +nan / 0 |
| USDCAD | −0.51 / 27 | +0.21 / 20 | +0.15 / 9 | −0.58 / 6 |
| AUDUSD | −0.33 / 19 | +0.23 / 25 | +0.55 / 15 | +1.37 / 6 |
| NZDUSD | −0.88 / 21 | −0.80 / 18 | −0.41 / 11 | −0.55 / 5 |

**0 GO, 2 SWEEPs** — EURUSD chain N≥1 (+2.05 / 18) and N≥2 (+1.19 /
10). GBPUSD's prior chain N≥2 SWEEP (+1.90 / 12 at H30e) collapses to
NO-GO. Standalone GBPUSD A SWEEP at +1.29 unchanged (H30f doesn't
touch the standalone path). The 2-SWEEP count is stable across
H30e → H30f but the *identity* of the SWEEP cells migrates from
GBPUSD to EURUSD chain-conditional — diagnostic of how sensitive
the SWEEP-tier signal is to chain-mode state-machine fidelity.
Detector substrate is structurally clean across both state machines
now; H31 regime-classifier remains the recommended direction.
27/27 tests pass (5 new H30f regressions). Detail:
results/H30_box_pattern_corrected.md § "H30f".

## Box detector third bug fix (H30e, 2026-06-20) — P0 = lowest low, 0 GO 2 SWEEP (both GBPUSD)

Dr. A's third visual catch: "Black arrow shows price's lowest-low which
is where point-0 should rest." Detector violated this on **103/265
boxes (39%) at H30d** — biggest gap was 5.42 dollars (chain id 5
idx 2). Two interacting causes: (1) new-high check ran BEFORE
invalidation, so wide-range bars with simultaneous new high + deeper
low skipped invalidation; (2) chain-cont gap `[prev_P2+1, prev_P3]`
was never scanned for deeper lows. Both fixed in
`_detect_box_corrected`, `_walk_first_box`, `_walk_chain_continuation`
(invalidation-first ordering + gap pre-scan in cont). Legacy detector
unaffected. 22/22 tests pass.

Verification: H30e DXY has **0/253 violators** (was 103/265). 100%
elimination.

H30b standalone (Variant A): GBPUSD A holds SWEEP +1.29/25 (was
+1.24/24 at H30d). DXY -0.50 (was -0.61), others within ±0.22.

H30c chain-conditional under H30e:

| Sym | H30b H30e | N≥1 OOS | N≥2 OOS | N≥3 OOS |
|---|---|---:|---:|---:|
| DXY    | −0.50 / 37 | −0.21 / 33 | −0.59 / 18 | −0.61 / 10 |
| EURUSD | −0.19 / 23 | +0.19 / 31 | −0.72 / 16 | −1.15 / 9 |
| **GBPUSD** | +1.29 / 25 SWEEP | +0.90 / 22 | **+1.90 / 12 SWEEP** | +0.35 / 6 |
| USDJPY | −0.13 / 27 | +0.78 / 19 | +0.23 / 8 | +0.05 / 3 |
| USDCAD | −0.51 / 27 | −0.66 / 24 | −1.06 / 13 | −0.82 / 6 |
| AUDUSD | −0.33 / 19 | +0.23 / 27 | +0.81 / 15 | +0.79 / 4 |
| NZDUSD | −0.88 / 21 | −0.32 / 20 | −0.31 / 15 | +0.09 / 8 |

**0 GO, 2 SWEEPs across (pair × lens) — both GBPUSD** (standalone A at
+1.29 and chain N≥2 at +1.90). Same pair, same direction, consistent
weak-positive signal that doesn't clear the GO bar. DXY chain context
stays negative, confirming H30d's invalidation of the buggy +3.34
headline. Honest verdict at H30e: single-box and chain-conditional
trade strategies are decisively NO-GO; the detector substrate is
structurally clean for downstream regime-classifier work. H31 remains
the recommended direction. Detail:
results/H30_box_pattern_corrected.md § "H30e".

## Box detector bug-fix pass (H30d, 2026-06-20) — H30c headlines invalidated, 0 GO 0 SWEEP everywhere

Dr. A flagged two detector bugs visible in the regenerated H30c figures:
(1) P3 marker plotted at the bar's actual high/low instead of P1's
level (visualization bug — fix: `p3_price = p1_price`); (2) "the box
is shallower than price action in all charts" — diagnostic showed 4/5
recent DXY panels had **P1_idx == P0_idx** (1-bar micro-boxes whose
swing was just the P0 bar's intra-bar range). Root cause: 50%-retrace
check could fire before `running_max` ever advanced past P0's own
value. Fix: gate retrace on a new `re_updated` flag in all three
corrected code paths. Legacy detector unaffected (find_peaks vets P1
by prominence).

DXY universe after fix: 397 → **265** boxes; **0 micro-boxes** remain;
**265/265 boxes** now have `p3_price == p1_price`. 20/20 tests pass
(2 new regression tests).

**Re-running both backtests invalidates the H30c "DXY N≥2 +3.34
SWEEP" headline — that was bug-driven micro-box inflation.**

H30b standalone Variant A (H30d-corrected):

| Sym | H30c | **H30d** | Δ |
|---|---:|---:|---:|
| DXY    | −0.23 / 30 | **−0.61 / 40** | −0.38 |
| EURUSD | +0.44 / 22 | **−0.17 / 25** | −0.61 |
| GBPUSD | +1.78 / 20 | **+1.24 / 24** SWEEP | −0.54 |
| USDJPY | −0.17 / 26 | **−0.15 / 29** | +0.02 |
| USDCAD | −0.41 / 22 | **−0.29 / 26** | +0.12 |
| AUDUSD | −0.37 / 19 | **−0.30 / 20** | +0.07 |
| NZDUSD | −0.81 / 20 | **−0.97 / 23** | −0.16 |

H30c chain-conditional (H30d-corrected):

| Sym | H30b H30d | N≥1 OOS | N≥2 OOS | N≥3 OOS |
|---|---|---:|---:|---:|
| DXY    | −0.61 / 40 | +0.35 / 36 | **+0.34 / 27** (was +3.34) | +0.57 / 20 |
| EURUSD | −0.17 / 25 | −1.32 / 26 | −1.15 / 21 | −0.97 / 17 |
| GBPUSD | +1.24 / 24 | +0.76 / 12 | +1.42 / 7 | +1.03 / 4 |
| USDJPY | −0.15 / 29 | −0.53 / 8 | −0.75 / 4 | −0.53 / 2 |
| USDCAD | −0.29 / 26 | +0.78 / 41 | +0.36 / 36 | +0.05 / 29 |
| AUDUSD | −0.30 / 20 | −0.28 / 26 | −0.40 / 22 | −0.63 / 20 |
| NZDUSD | −0.97 / 23 | −0.48 / 29 | −0.58 / 23 | −0.61 / 16 |

**0 GO, 0 SWEEP across the entire (pair × lens) matrix.** GBPUSD A
standalone (+1.24 SWEEP) is the only cell that remains above the +1.0
NO-GO floor. The H30c "DXY chain context lifts Sortino over the GO
floor" claim is retracted — it was a measurement artifact.

Honest verdict: **the box-pattern single-box and chain-conditional
trade strategies are decisively NO-GO** across H29 / H30a / H30b /
H30c / H30d. Dr. A's bug catch prevented a false-positive shipping
claim. Detector is cleaner; H31 regime-classifier remains the
recommended direction. Detail:
results/H30_box_pattern_corrected.md § "H30d".

## Box chaining and reversal (H30c, 2026-06-20) — DXY OOS Sortino +3.34 at N≥2 (SWEEP only because 17<30 trades) — INVALIDATED BY H30d BUG FIX

Dr. A extended the rule with same-direction chaining (P0 of box-N+1 = P2
of box-N) and reversal detection (opposite-direction box anchored at the
chain's terminal extreme ends the chain). Implemented in
`_detect_box_chained`, wired via `detect_boxes_df(chain_mode=True)`.
After each box confirms, a continuation candidate races a reversal
candidate; first to confirm wins. 18/18 unit tests pass (4 new).

Chain-conditional backtest (`scripts/h30c_chain_conditional.py`):
trade only when chain_index ≥ K for K ∈ {0, 1, 2} corresponding to
N≥1, N≥2, N≥3.

| Sym | H30b OOS | N≥1 OOS | N≥2 OOS | N≥3 OOS |
|---|---|---|---|---|
| DXY    | −0.23 / 30 | **+2.14 / 43** | **+3.34 / 17** SWEEP | +0.12 / 7 |
| EURUSD | +0.44 / 22 | −0.54 / 27 | −0.39 / 16 | −0.35 / 8 |
| GBPUSD | +1.78 / 20 | +0.50 / 29 | +0.74 / 12 | +1.90 / 4 |
| USDJPY | −0.17 / 26 | −0.05 / 32 | +0.03 / 21 | **+1.32 / 11** SWEEP |
| USDCAD | −0.41 / 22 | −0.41 / 21 | −0.86 / 14 | −1.12 / 11 |
| AUDUSD | −0.37 / 19 | +0.78 / 26 | +0.18 / 19 | +0.37 / 14 |
| NZDUSD | −0.81 / 20 | −0.69 / 36 | −0.39 / 25 | −0.35 / 18 |

**DXY's response is the cleanest signal of "chain context matters" in
the whole arc.** OOS Sortino lifts from H30b −0.23 → +3.34 at N≥2 (the
+3.0 GO Sortino floor cleared) but only 17 OOS trades < 30 GO trade
floor → SWEEP, not GO. The locked rule binds on trade count, not
Sortino; one more OOS year would likely tip it. USDJPY also lifts at
N≥3 (+1.32 SWEEP), AUDUSD off the floor at N≥1 (+0.78). GBPUSD
regresses — its H30b SWEEP was carried by first-of-chain boxes.
EURUSD/USDCAD/NZDUSD: unmoved NO-GO.

DXY chain shape: 397 boxes in 198 chains; longest chain 3 boxes; 197
chains start with a reversal. No 5+box continuations in 36 years of
daily history.

**0 cells GO across (pair × lens).** Three SWEEPs (DXY N≥1, DXY N≥2,
USDJPY N≥3) — first cells anywhere in the box arc to cross the +1.0
NO-GO Sortino floor. No hurst-agent change; live cron untouched.
Standalone H30b detector preserved (chain_mode=False) so H30a/H30b
results stay reproducible. Detail:
results/H30_box_pattern_corrected.md § "Box chaining and reversal".

## Box-pattern detector P1 algorithm fix (H30b, 2026-06-20) — GBPUSD A flips to SWEEP, still 0/7 GO

Dr. A flagged a structural detector bug: legacy nominated P1 from
``find_peaks``'s pre-computed local extrema and locked at the FIRST
prominent peak after P0. Dominant impulses with intermediate prominent
peaks got the wrong geometry (the 2008 DXY rally: P0=75.7 Sep '08,
intermediate peak ≈82 early Oct, dominant ≈88 late Oct → legacy locked
P1=82). Corrected algorithm: walk forward from each P0 maintaining a
running extreme; P1 only locks when the 50% retrace from the *current*
running extreme triggers. Invalidation (new lower low / higher high)
respawns a new P0 at that bar. Single-candidate-at-a-time order to
preserve the deeper, structurally meaningful P0 against intermediate
``find_peaks`` troughs. Legacy detector preserved via ``legacy=True``.
14/14 tests pass.

Detector universe grew ~3× per pair on DXY 170 → 275 LONG boxes (boxes
previously eaten by mega-box dedup + locked-at-first-peak P1 path now
enumerate as their own structures). OOS Sortinos shifted:

| Symbol | A H30a / n | **A H30b / n** | Δ | B H30b / n |
|---|---:|---:|---:|---:|
| DXY    | −0.90 / 29 | **−0.23 / 30** | +0.67 | −0.12 / 30 |
| EURUSD | −1.48 / 29 | **+0.44 / 22** | +1.92 | +0.70 / 22 |
| GBPUSD | −0.38 / 18 | **+1.78 / 20 SWEEP** | +2.16 | +0.41 / 20 |
| USDJPY | −0.63 / 28 | **−0.17 / 26** | +0.46 | −0.45 / 26 |
| USDCAD | +0.11 / 19 | **−0.41 / 22** | −0.52 | −0.51 / 22 |
| AUDUSD | +0.61 / 32 | **−0.37 / 19** | −0.98 | −0.48 / 19 |
| NZDUSD | −0.59 / 28 | **−0.81 / 20** | −0.22 | −0.91 / 20 |

**GBPUSD Variant A flips NO-GO → SWEEP** (OOS Sortino +1.78 on 20 trades)
— first crossing of the +1.0 NO-GO floor anywhere in the box arc. Well
below the +3.0 GO floor; still 0/7 GO across both variants. Detector fix
is correct and visible in the regenerated figures (no mega-box; 218-bar
clean LONG appears in the recent-5 DXY panel). H31 regime-classifier
direction remains the right move with a ~3×-denser substrate. Detail:
results/H30_box_pattern_corrected.md.

## Box-pattern signal corrected spec (H30a, 2026-06-20) — 0/7 GO across BOTH variants, healthy trade counts

Dr. A flagged two errors in H29 (T1/2 used (P0+P3)/2 — contaminated by
breakout phase; detector had no max-length cap → produced a 1024-bar
mega-box). H30 fixes both. T1/2 = (P0+P2)/2 by default; max_length=250.
Box-to-trade now supports two target ladders: **Variant A** (Dr. A's
primary: 1.618/2.345/3.456 × height, anchored at P2) and **Variant B**
(1.618/2.236/3.618 × height, anchored at P1). 8/8 unit tests.

A-old = original H30 (3 targets, no effective trail). A-new = 2026-06-20
tightening (2 targets 1.618/2.236, trail at P2 + 2.200·height). B
unchanged.

| Symbol | H29 OOS / n | A-old OOS / n | **A-new OOS / n / MDD** | B OOS / n / MDD | All decisions |
|---|---|---|---|---|---|
| DXY    | −0.46 /  3 | −0.78 / 29 | **−0.90 / 29 / −17.8%** | −0.89 / 31 / −18.7% | NO-GO |
| EURUSD |   n/a /  0 | −1.42 / 29 | **−1.48 / 29 / −22.0%** | −1.20 / 32 / −24.2% | NO-GO |
| GBPUSD | −1.21 /  2 | −0.70 / 18 | **−0.38 / 18 / −6.4%**  | −0.56 / 18 / −9.4%  | NO-GO |
| USDJPY | −0.76 /  2 | −0.40 / 28 | **−0.63 / 28 / −11.3%** | −0.39 / 30 / −10.0% | NO-GO |
| USDCAD | +0.43 /  4 | −0.17 / 19 | **+0.11 / 19 / −5.6%**  | −0.12 / 21 / −7.0%  | NO-GO |
| AUDUSD | −0.19 /  6 | +0.32 / 32 | **+0.61 / 32 / −8.3%**  | +0.70 / 32 / −9.0%  | NO-GO |
| NZDUSD | −1.65 /  6 | −0.12 / 28 | **−0.59 / 28 / −10.7%** | +0.10 / 29 / −10.7% | NO-GO |

Did the T3 cut help or hurt A? **Mixed, net trivial** on Sortino (mean Δ
+0.01, median −0.06; 3 pairs helped, 4 hurt). But the early trail
activation IS doing something visible: **A-new MaxDD beats B's on 5/7
pairs**. Trail protects drawdown by ratcheting the stop near T2_A; the
right-tail cost (runners that would have gone to A-old's 3.456× target
get trail-stopped earlier) partly washes the drawdown win out of
Sortino. B still slightly edges A-new on Sortino (4 wins vs 2 vs 1
tie). Neither variant clears GO on any pair.

Detection became ~3–6× more granular (the cap fixes a dedup artifact
that hid sub-boxes inside mega-boxes); OOS trade counts now sit at
18–32 per pair — well above the 10 NO-GO floor — so the negative is
NOT a small-n alibi. OOS Sortinos converged toward zero (range −1.42
to +0.70). Variant B slightly out-performs A on 6/7 pairs (B anchors
targets at P1, higher than P2, capturing more right tail when trades
work; still not enough to flip any pair). The single-box trade trigger
is shipped NO-GO with high confidence; the detector is now a stronger
research asset (cleaner visuals — no mega-box) for the H31 regime-
classifier use. Detail: results/H30_box_pattern_corrected.md.

## Box-pattern signal H29 (2026-06-18) — 0/7 GO under original spec

Dr. A's 4-point box signal (P0 swing low → P1 swing high → P2 50%
retrace → P3 break of P1) + Hurst time-asymmetry filter (take LONG only
when P1.idx > T-mid). Implemented in `src/rsi_pattern/box_pattern.py`
with 5/5 unit tests + DXY mechanics audit. **Detection is faithful, the
bias rule does not produce edge** at the locked floors on any of the 7
FX symbols:

| Symbol | Universe (long boxes) | Aligned (P1>T-mid) | Trades | OOS Sortino | Box decision |
|---|---:|---:|---:|---:|---|
| DXY    | 34 |  6 |  5 | −0.46 | NO-GO |
| EURUSD | 51 |  5 |  4 |  n/a (OOS n=0) | NO-GO |
| GBPUSD | 51 |  7 |  7 | −1.21 | NO-GO |
| USDJPY | 24 |  2 |  2 | −0.76 | NO-GO |
| USDCAD | 20 |  2 |  2 | +0.43 | NO-GO |
| AUDUSD | 87 | 11 | 11 | −0.19 | NO-GO |
| NZDUSD | 83 | 14 | 14 | −1.65 | NO-GO |

The bias filter passes ~10–18% of detected boxes, and surviving trades
cluster around Sortino ≈ −0.5 — the time-asymmetry rule as spec'd does
not predict subsequent uptrends on FX daily. Confluence with M-P1 LONG:
**0% same-day overlap on every symbol** — the two signals are
mechanically orthogonal (a useful prior if the box rule is ever
revived). No hurst-agent change. Module kept as a research asset
(future H30 candidate: inverted bias rule). Detail:
results/H29_box_pattern_validation.md.

## Per-symbol notes

### EURUSD — GO (solid). H23 (2026-05-19)
yfinance `EURUSD=X`, 5,827 daily bars 2003-12-01→2026-05-18. IS Sortino
+3.27 ≈ OOS +4.06 (no IS/OOS degradation — the USDMXN failure mode is
absent). OOS MaxDD −1.6%. Cleanest transfer of the six.
**Gotcha:** none specific. EURUSD=X is quoted to 4–5 dp; FLD cycles are in
*bar* units (10/20/40 daily bars), unaffected by quote precision.

### USDCAD — GO (solid). H23 (2026-05-19)
yfinance `USDCAD=X`, 5,895 daily bars 2003-09-17→2026-05-18. OOS +3.12 on
15 trades — the *most* OOS trades of any GO pair, so the most trustworthy
OOS estimate. Full +4.36 / 35.
**Gotcha:** USDCAD is a USD-base pair (like USDJPY); the long-only engine
is buying CAD weakness / USD strength. Worked here, but watch for the same
long-only-bias risk that sinks USDJPY if behaviour regime-shifts.

### GBPUSD — THIN GO. H23 (2026-05-19) → H24 (2026-05-19)
yfinance `GBPUSD=X`, 5,839 daily bars 2003-12-01→2026-05-18. H23 OOS
+5.57 / 9 trades, full +4.91 / 34. **H24 robustness pass: 2/4 conditions
hold → stays THIN GO.** Passed Gini (0.697 ≤ 0.7) and per-trade
sensitivity (min Sortino +2.84 even dropping its largest trade — NOT a
one-trade artifact). Failed bootstrap (decision p5 +0.00 / finite +0.90 <
+3.0) and rolling stability (2/4 windows; 2019→2023 sub-window Sortino
+0.02). Edge is real but **regime-concentrated post-2023**, not
stationary. **Do NOT flip `enabled: true`** — a clean flip needs the
post-2023 behaviour to persist into a true *forward* window (~12 months
live-paper), not more in-sample slicing. See results/H24_thin_go_
robustness.md.

### NZDUSD — SWEEP (downgraded). H23 (2026-05-19) → H24 (2026-05-19)
yfinance `NZDUSD=X`, 5,828 daily bars 2003-12-01→2026-05-18. H23 OOS
+5.34 / 4 trades. **H24 robustness pass: 0/4 conditions hold →
DOWNGRADED GO → SWEEP.** Three of four OOS trades are full −1R losers;
the entire positive Sortino is the single 2024-05-01 trade (+17.4R, 3×).
Drop it → Sortino −0.66. 100% of profit in one 30-day window; Gini 0.93.
The H23 GO was a 4-sample mirage — exactly the artifact the no-spurious-
ship doctrine exists to catch. Not rejected outright (full-sample H23
+4.42 / 35 is genuinely positive); parked at `sweep_needed` pending a
real forward-OOS follow-up, NOT a parameter re-tune (out of scope). See
results/H24_thin_go_robustness.md.

### AUDUSD — SWEEP (structural). H23 (2026-05-19)
yfinance `AUDUSD=X`, 5,203 daily bars 2006-05-16→2026-05-18. OOS +1.85,
full +2.21 / 33. Excluding 2008 the full Sortino *falls* to +1.33 — the
edge **leans on** the GFC carry unwind (episode-dependent, not continuous).
Closest H24 variants (NOT run): FLD (15,30,60); loose-M dip 50→45; both.

### USDJPY — SWEEP (structural). H23 (2026-05-19)
yfinance `USDJPY=X`, 7,661 daily bars 1996-10-30→2026-05-18. Richest
universe (47 full / 16 OOS) so trade count is not the issue. OOS +1.64.
Excluding BOJ/MoF intervention years {2003,2004,2011,2022,2024} barely
moves it (+1.34→+1.75) so interventions are not the core issue either.
**Structural:** long-only engine vs. JPY's durable USD-up trend regime —
long M-top entries fade into trend continuation. Needs a regime/trend
overlay (NOT a knob sweep, and NOT a short-side flip — H21/H22 nulled
short-side). H24 scope.

### USDSEK, USDZAR — NOT RUN
Exotic-FX microstructure (wider/again spreads, thinner books, policy
discontinuities) needs separate calibration. The two borderline majors
above fail for *structural* reasons, not microstructure — exotics would be
worse. Deliberately not chased; revisit only with an exotic-specific spec.

## Gotchas that apply to ALL pairs

- **FLD cycles are bar units, not pips/price.** `(10,20,40)` = 10/20/40
  daily bars regardless of the pair's quote convention or decimal places.
- **USD-base vs USD-quote matters for the long-only engine.** USD-quote
  pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD) → a long is "USD weakness".
  USD-base pairs (USDJPY, USDCAD) → a long is "USD strength". The engine
  does not know the difference; it just trades RSI M-tops long. Pairs whose
  edge depends on a *persistent* USD direction (USDJPY) are the ones that
  break. This is the single best predictor of transfer success here.
- **yfinance FX history is shorter than DXY.** Majors start 2003–2006 vs
  DXY 1990; the 70/30 OOS slice is ~6–7y and trade-thin for some pairs.
  Always read OOS trade count alongside OOS Sortino.
- **Spread:** H23 uses the H12/H15 daily convention (2 bps in the writeup
  context; per-trade R already reflects `simulate_fib_trade` exits). For
  *retail* FX execution bump to ~15 bps before treating any of these as a
  live retail strategy (same caveat already recorded for USDMXN).
