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

## Box-pattern signal corrected spec (H30, 2026-06-20) — 0/7 GO across BOTH variants, healthy trade counts

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
