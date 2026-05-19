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

| Symbol | Class | Decision | OOS Sortino | OOS Tr | Full Sortino | Full Tr | Exp. | Live? |
|---|---|---|---:|---:|---:|---:|---|---|
| DXY | index | GO (shipped) | +5.38 (7y) / +1.34 (70/30)† | 14 / 19 | +5.75 | 56 | H12/H15 | **yes** (`enabled: true`) |
| USDMXN | fx_emerging | SWEEP | +2.53 | — | +4.41 | 26 | H15/H16 | no |
| USDCHF | fx_major | NO-GO | — | — | +0.87 | 25 | H15 | no |
| EURUSD | fx_major | **GO** | +4.06 | 12 | +3.15 | 30 | H23 | no (`enabled: false`) |
| USDCAD | fx_major | **GO** | +3.12 | 15 | +4.36 | 35 | H23 | no (`enabled: false`) |
| GBPUSD | fx_major | **GO ⚠ thin-OOS** | +5.57 | 9 | +4.91 | 34 | H23 | no (`enabled: false`) |
| NZDUSD | fx_major | **GO ⚠⚠ provisional** | +5.34 | 4 | +4.42 | 35 | H23 | no (`enabled: false`) |
| AUDUSD | fx_major | SWEEP | +1.85 | 9 | +2.21 | 33 | H23 | no |
| USDJPY | fx_major | SWEEP | +1.64 | 16 | +1.34 | 47 | H23 | no |
| USDSEK | fx_exotic | NOT RUN | — | — | — | — | — | no |
| USDZAR | fx_exotic | NOT RUN | — | — | — | — | — | no |

† DXY shipped on the H15 full-sample decision and a 7-year OOS window
(+5.38). Under the *stricter* H23 70/30 split DXY itself is only SWEEP
(OOS +1.34) — i.e. the H23 bar is harder than the bar DXY cleared.

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

### GBPUSD — GO ⚠ thin-OOS. H23 (2026-05-19)
yfinance `GBPUSD=X`, 5,839 daily bars 2003-12-01→2026-05-18. OOS Sortino
+5.57 but on only **9 OOS trades** (below the n<10 small-sample line).
Full sample robust (+4.91 / 34), IS (+5.51) ≈ OOS — directionally a clean
GO but the OOS Sortino is a 9-sample figure. Brexit-year (2016) exclusion
does not change the full-sample number. **Do NOT flip `enabled: true`
before an H24 OOS-robustness pass.**

### NZDUSD — GO ⚠⚠ provisional. H23 (2026-05-19)
yfinance `NZDUSD=X`, 5,828 daily bars 2003-12-01→2026-05-18. OOS Sortino
+5.34 rests on **only 4 OOS trades**, mean R +11.31 — one or two trades
dominate; the OOS slice is statistically meaningless on its own. The GO is
carried by the strong *full* sample (+4.42 / 35) and IS (+4.70 / 31), not
the OOS slice. **Provisional. Must NOT be flipped live without H24
confirming the edge on a non-degenerate OOS sample.**

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
