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
| BTCUSD | crypto | NO-GO (H26) | +0.65 | 5 | +8.30 | 26 | H26 | no | NOT RUN | — |
| ETHUSD | crypto | NO-GO¹ (H26, trade-count only) | **+12.55** | 7 | +19.63 | 25 | H26 | no | NOT RUN | — |
| SOLUSD | crypto | NO-GO (H26, data-constrained) | −0.45 | 4 | +4.11 | 13 | H26 | no | NOT RUN | — |
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
