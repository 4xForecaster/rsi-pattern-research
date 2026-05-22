# H27 — Crypto Cycle/Cadence Recalibration

**Date:** 2026-05-21
**Script:** [`scripts/h27_crypto_cycle_recalibration.py`](../scripts/h27_crypto_cycle_recalibration.py)
**Run dump:** [`results/_h27_run.json`](_h27_run.json)
**Figures:** [`figures/20_crypto_cycle_recon.png`](../figures/20_crypto_cycle_recon.png),
[`figures/21_crypto_cadence_sweep.png`](../figures/21_crypto_cadence_sweep.png)

## TL;DR

H26 said crypto's M-P1 *edge* looked real (ETH OOS Sortino +12.55, no
degradation) but failed on trade count, and teed up "recalibrate the FLD
cycle ladder." **H27 falsifies that specific hypothesis and identifies the
true lever:**

1. **The FLD ladder is a NULL lever.** It does not change the trade
   universe — only Scheme-D sizing. No ladder can lift crypto to the
   trade-count floors.
2. **The detection CADENCE is the real lever.** Shortening RSI + scaling
   the M timing windows grows the universe and preserves the edge — for
   ETH/SOL it lifts them off the floor.
3. **Net verdict: still 0 GO under the conservative primary rule.** ETH-USD
   on a crypto cadence is a credible **forward-test candidate** (clears the
   secondary PRAGMATIC rule, robustness THIN 2/4) — promoted to a
   forward/paper watchlist, **NOT** the live config. Nothing ships.

## Overfitting disclosure (read this first)

The cadence candidates were glimpsed against OOS during exploratory
probing before this script was written. To stay honest:
- the **primary** crypto cadence is **theory-chosen** (recon, below), and
  is the **moderate RSI9** — deliberately **not** the best-OOS RSI7
  (anti-cherry-pick guard; RSI7 actually scores higher on ETH/SOL OOS);
- RSI7 is reported only as a **sensitivity** row;
- anything that clears GO is treated as a **forward-test candidate**
  (`enabled:false`, robustness-gated), never a live ship, because the OOS
  is no longer pristine and crypto history is short. The clean arbiter is
  **forward data**, which H27 cannot manufacture.

## Finding 1 — the FLD ladder is a null lever

The M-top trade **universe** is set by RSI M-detection; the FLD ladder
only drives the Scheme-D bias multiplier (0/1/3). OOS universe across four
ladders `(10,20,40)`, `(5,10,20)`, `(8,16,32)`, `(6,12,24)`:

| Symbol | OOS universe (all 4 ladders) | trades range | OOS Sortino range |
|---|---:|---|---|
| BTCUSD | **24 (invariant)** | 5–9 | +0.47 … +1.71 |
| ETHUSD | **16 (invariant)** | 7–8 | +7.29 … +12.55 |
| SOLUSD | **7 (invariant)** | 3–5 | −0.66 … −0.24 |

ETH's surviving trades **max at 8 under every ladder** — below the 10-trade
NO-GO floor. **No FLD ladder can ever make crypto GO.** The teed-up
hypothesis is dead; the ladder is held at `(10,20,40)` for the rest of H27.

## Recon (IS-only periodogram — theory input, not performance)

Dominant IS periods (bars), top-8 in [3, 160]:

- **BTCUSD**: [3.3, 5.4, 8.4, 9.0, 15.2, 17.9, 20.7, 60.9]
- **ETHUSD**: [3.1, 3.1, 3.3, 3.4, 3.4, 14.3, 90.8, 114.6]
- **SOLUSD**: [3.0, 3.9, 4.8, 7.6, 8.3, 8.3, 26.4, 104.0]

Crypto's tradeable spectral energy sits well below FX's — concentrated at
**~3–9 & ~15–20 bars** (plus a long macro band). FX's RSI-14 oscillator is
slow for this. Theory-derived crypto cadence: a shorter oscillator with
proportionally shorter pattern windows. Pre-registered primary = **RSI9,
windows ~0.64×** (moderate); sensitivity = RSI7, ~0.5×.

## Finding 2 — the detection cadence is the real lever

Faithfulness gate: **D0 (RSI14) reproduces H26 exactly** — BTC 5t/+0.65,
ETH 7t/+12.55, SOL 4t/−0.45. ✓

| Symbol | Cadence | OOS univ | OOS trades | OOS Sortino | STRICT | PRAGMATIC | Robustness |
|---|---|---:|---:|---:|---|---|---|
| BTC | D0 RSI14 | 24 | 5 | +0.65 | NO-GO | NO-GO | — |
| BTC | **D1 RSI9** (primary) | 36 | 18 | +0.98 | NO-GO | NO-GO | — |
| BTC | D2 RSI7 | 41 | 19 | +0.72 | NO-GO | NO-GO | — |
| ETH | D0 RSI14 | 16 | 7 | +12.55 | NO-GO | SWEEP | — |
| ETH | **D1 RSI9** (primary) | 23 | 12 | +6.19 | SWEEP | **GO** | **THIN 2/4** |
| ETH | D2 RSI7 | 27 | 16 | +7.53 | SWEEP | **GO** | **THIN 2/4** |
| SOL | D0 RSI14 | 7 | 4 | −0.45 | NO-GO | NO-GO | — |
| SOL | **D1 RSI9** (primary) | 16 | 12 | +3.79 | SWEEP | SWEEP | — |
| SOL | D2 RSI7 | 19 | 13 | +3.68 | SWEEP | **GO** | **0/4 → downgraded** |

**Cadence grows the universe** (BTC 24→41, ETH 16→27, SOL 7→19) — the
mechanism H26 predicted. Reads:

- **ETHUSD — forward-test candidate.** Crypto cadence lifts it from
  NO-GO(D0) to PRAGMATIC GO with OOS Sortino +6.19 (RSI9) / +7.53 (RSI7)
  on 12–16 trades, robustness THIN (2/4). Strong and consistent across
  cadences — but STRICT is still SWEEP (12–16 < 30 OOS trades) and the OOS
  was peeked. **Promote to forward/paper watchlist; do not ship live.**
- **SOLUSD — null after robustness.** RSI9 is SWEEP both rules; RSI7's
  PRAGMATIC GO is a **cluster artifact** (robustness 0/4) — correctly
  killed. The robustness gate still works on crypto. SOL is not tradeable
  here yet (history too short, edge too concentrated).
- **BTCUSD — no OOS edge at any cadence.** Universe grows but Sortino
  stays ~+0.7–1.0 → NO-GO under both rules, all cadences. BTC's
  2022-11→2026 OOS simply lacks the M-P1 long edge, independent of
  sampling.

## Decisions (load-bearing, documented — autonomous, no questions)

- **PRIMARY rule (RSI9 / STRICT OOS-trade): 0 GO.** No crypto symbol
  clears the conservative bar. Consistent with the program doctrine that
  OOS is load-bearing.
- **No hurst-agent integration, no live-config change.** ETH only clears
  the *secondary* PRAGMATIC rule, robustness is THIN, and the OOS is
  contaminated by exploratory peeking. Adding it (even `enabled:false`)
  would assert a GO classification the primary evidence does not support.
  The live DXY cron is untouched.
- **ETH-USD recorded as an H28 forward-test candidate** in
  `docs/SYMBOLS_TESTED.md` — the clean test is forward data with the
  pre-registered RSI9 crypto cadence, not more in-sample slicing.
- **The detector cadence is now a known, validated lever** for the whole
  program — a result that outlives crypto (it explains *why* low-N symbols
  fail and how to grow their universe without touching the edge logic).

## Net read

The literal H27 (FLD recalibration) was a dead end — proven, not assumed.
The pivot to detection cadence is the real finding: it grows the trade
universe and confirms crypto's M-P1 long edge is genuine but historically
under-sampled. **ETH-USD is the first crypto worth a forward test** (RSI9
crypto cadence). Until a true forward window confirms it, nothing ships,
and the conservative verdict stands at **0 GO**. Highest-leverage next
step (**H28**): stand up a forward/paper tracker for ETH-USD on the RSI9
cadence and let unseen data adjudicate — the only test the OOS-peeking
here cannot contaminate.
