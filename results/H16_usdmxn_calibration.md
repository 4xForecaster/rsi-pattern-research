# H16 Part 2 — USDMXN Calibration Sweep

**Date:** 2026-05-12

H15 left USDMXN at Sortino +4.41 / 26 trades on the full sample (SWEEP —
Sortino qualified, trade count 4 short of the 30-floor). This step runs
the three calibration variants flagged in H15's writeup to see if any
flips USDMXN to GO. **Spoiler: none do, and most make it worse.**

## Protocol

- **Data**: USDMXN daily from yfinance `MXN=X` (cached at
  `data/yfinance_cache/MXN_X_daily.csv`), 5,838 bars,
  2003-12-01 → 2026-05-04.
- **Split**: first 70% IS (2003-12 → 2019-08), last 30% OOS (2019-08 → 2026-05).
- **Variants** (everything else held at Scheme D defaults):
  - **baseline** — H15 config, `dip≥50`, FLD cycles `(10, 20, 40)`
  - **variant A** — `dip≥45` (capture shallower retraces), cycles unchanged
  - **variant B** — `dip≥50`, cycles `(15, 30, 60)` (peso ≈120-day risk cycle)
  - **variant C** — both A + B
- **GO threshold** (applied on OOS metrics — load-bearing):
  - **STRICT**: OOS Sortino ≥ 3.0 AND OOS trades ≥ 30 AND OOS Max DD > −10%
  - **PRAGMATIC**: OOS Sortino ≥ 3.0 AND **full-sample** trades ≥ 30 AND OOS Max DD > −10%

The PRAGMATIC variant exists because USDMXN's signal frequency is ~1.2
trades/year; reaching 30 trades on a 6.8-year OOS window is essentially
impossible (≈4 trades/year required). Allowing full-sample trade count
keeps the sample-size proxy intact while still demanding OOS robustness
on Sortino and DD.

## Results

| Variant | Slice | Trades | Mean R | Total R/yr | Sharpe | **Sortino** | Max DD |
|---|---|---:|---:|---:|---:|---:|---:|
| **baseline** | IS  | 19 | +5.66 | +8.03 | +0.44 | **+5.30** | −2.41% |
| **baseline** | OOS |  7 | +3.61 | +5.69 | +0.51 | **+2.53** | −5.23% |
| **baseline** | FULL | 26 | +5.11 | +6.85 | +0.41 | +4.41 | −2.70% |
| variant_A (dip=45) | IS  | 20 | +5.33 | +7.95 | +0.43 | +5.09 | −2.43% |
| variant_A (dip=45) | OOS |  9 | +2.37 | +4.79 | +0.43 | **+1.73** | **−8.72%** |
| variant_A (dip=45) | FULL | 29 | +4.41 | +6.59 | +0.39 | +3.94 | −4.52% |
| variant_B (cycles=15/30/60) | IS  | 16 | +5.26 | +6.27 | +0.35 | +4.05 | −3.38% |
| variant_B (cycles=15/30/60) | OOS |  7 | +0.53 | +0.84 | +0.20 | **+0.37** | −5.69% |
| variant_B (cycles=15/30/60) | FULL | 24 | +3.78 | +4.67 | +0.30 | +3.03 | −3.38% |
| variant_C (both) | IS  | 17 | +4.77 | +6.05 | +0.33 | +3.14 | −3.48% |
| variant_C (both) | OOS | 10 | −0.10 | −0.22 | −0.03 | **−0.04** | **−9.49%** |
| variant_C (both) | FULL | 28 | +2.96 | +4.27 | +0.28 | +2.27 | −5.28% |

## Decisions

| Variant | Decision | Reason |
|---|---|---|
| baseline | **SWEEP** | OOS Sortino +2.53 < 3.0; trades insufficient (OOS 7, full 26) |
| variant_A | SWEEP | OOS Sortino +1.73 < 3.0; trades insufficient (OOS 9, full 29) |
| variant_B | SWEEP | OOS Sortino +0.37 < 3.0; trades insufficient (OOS 7, full 24) |
| variant_C | SWEEP | OOS Sortino −0.04 < 3.0; trades insufficient (OOS 10, full 28) |

None clear GO under either STRICT or PRAGMATIC. **Spec status stays
`sweep_needed`.** Closest to clearing: **the baseline itself.**

## Reading

1. **The H15 full-sample +4.41 Sortino was IS-biased.** Honest OOS for
   the same config is +2.53 — below the +3.0 ship-floor. The full-sample
   number was buoyed by the 2003–2019 stretch (IS Sortino +5.30).

2. **Variant A (looser dip) adds noise, not signal.** OOS Sortino drops
   from +2.53 to +1.73; OOS Max DD nearly doubles (−5.23% → −8.72%). The
   3 extra trades it picks up under-perform.

3. **Variant B (peso-cycle FLD) is catastrophic on OOS.** OOS Sortino
   collapses to +0.37. The (15, 30, 60) ladder may be canonical for
   peso macro cycles but does not coincide with the RSI M-P1 setup's
   signal structure — the FLD bias label loses its discriminative power
   on intraday trade entries.

4. **Variant C compounds the damage.** OOS Sortino goes *negative*.
   When both knobs are wrong, they don't average out — they stack.

5. **The IS/OOS split exposes regime instability.** Even the unchanged
   baseline shows a 2× degradation in Sortino IS→OOS (+5.30 → +2.53).
   That degradation is the same direction & magnitude that DXY's H12
   exhibits (DXY full +5.75, DXY OOS +5.38 — much smaller drop, but
   same sign). USDMXN's setup is intrinsically less stable across
   regime boundaries; this is a real property of the symbol, not a
   parameter-tuning failure.

6. **Cannot distinguish regime change from sample-size noise.** OOS
   has only 7 trades baseline. Three plausible explanations for the
   degradation:
   - (a) Peso behavior shifted post-2020 (USDMXN structurally different
     now)
   - (b) 7-trade samples have huge confidence intervals; noise
   - (c) Strategy edge genuinely decayed
   No way to discriminate without more data.

## What I did NOT try (and why)

User capped the sweep at 3 variants: *"If 3 doesn't clear the bar, the
problem is structural (volatility regime, USD-MXN trend asymmetry), not
parameter tuning. Document and stop."* Stopping per that rule.

Things that might help structurally (out-of-scope here, listed for
future-you):
- **Short-side variant** — USDMXN's bullish bias (33/59 trade universe)
  suggests the asymmetry is "USD trends up against MXN, peso weakens";
  the natural setup may be V-pattern shorts rather than M-pattern longs.
- **Regime overlay** — gate USDMXN signals on a multi-month USD-trend
  indicator (similar to the daily→5m gate in H14's Scheme G).
- **Trade-cluster aggregation** — H15 had several near-simultaneous M
  completions clustered around peso stress events; aggregating those
  into one position rather than firing each independently might improve
  the unit-of-risk count.

## Config disposition

USDMXN's `status` in `hurst-agent/config/rsi_m_p1.yaml` stays
**`sweep_needed`**. `enabled: false`. No code-side override mechanism
added — there's no winning param set to lock in.

Updated the `notes:` field for USDMXN to reflect H16 findings (was
"likely flips to GO with small sweep" — now "H16 sweep ran; none of
the three documented variants improved OOS metrics").

## Code

- [`scripts/h16_usdmxn_calibration.py`](../scripts/h16_usdmxn_calibration.py) — reproducible runner
- `results/_h16_usdmxn_run.json` — raw IS/OOS/FULL metric dump for all 4 cells

Reproducible: `python3 scripts/h16_usdmxn_calibration.py`
