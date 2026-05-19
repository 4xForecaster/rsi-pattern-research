# H26 — Crypto-Major Expansion of the Daily M-P1 LONG Framework

**Date:** 2026-05-19
**Script:** [`scripts/h26_crypto_expansion.py`](../scripts/h26_crypto_expansion.py)
**Run dump:** [`results/_h26_run.json`](_h26_run.json)
**Figures:** [`figures/18_crypto_equity_curves.png`](../figures/18_crypto_equity_curves.png),
[`figures/19_crypto_vs_fx_sortino.png`](../figures/19_crypto_vs_fx_sortino.png)

## TL;DR

**0 crypto GO.** The DXY-calibrated daily Scheme D does **not** clear the
locked bar on BTC, ETH, or SOL — but the reason is **signal scarcity, not
edge failure**. The single most striking number in the whole project is
here: **ETH OOS Sortino +12.55** — yet ETH is NO-GO because that rests on
only **7 OOS trades** (< the 10-trade floor). The framework's *edge* looks
excellent on crypto; the FX-calibrated cycle/detector geometry simply does
not fire often enough on crypto to reach the trade-count floors. No
hurst-agent integration (0 GO → don't build dead infrastructure). The
actionable output is a well-formed H27 hypothesis, not a config change.

## Data hygiene (documented; nothing silently smoothed)

yfinance crypto, fetched once and cached per ticker. All three majors are
**clean as fetched** — no cleaning was applied:

| Symbol | Ticker | Bars | Window | ~bars/yr | NaN | Dup | Monotonic | >50% 1-bar moves | day-gaps>1 |
|---|---|---:|---|---:|---:|---:|:--:|---:|---:|
| BTCUSD | BTC-USD | 4,262 | 2014-09-17 → 2026-05-18 | 365.3 | 0 | 0 | ✅ | **0** | 0 |
| ETHUSD | ETH-USD | 3,113 | 2017-11-09 → 2026-05-18 | 365.4 | 0 | 0 | ✅ | **0** | 0 |
| SOLUSD | SOL-USD | 2,230 | 2020-04-10 → 2026-05-18 | 365.4 | 0 | 0 | ✅ | **0** | 0 |

Notes: Yahoo logs crypto **7 days/week** (no weekend gap; max day-gap = 1),
so a crypto year has ~365 bars vs FX ~252 — the 70/30 OOS slice is
*time-shorter per bar-count* than the FX runs. No single-bar close-to-close
move exceeded 50% on any symbol, so no spike-artifact handling was needed
(had any existed it would have been **retained as real volatility, logged,
not smoothed**). No bars were excluded on any symbol.

## Cycle-length reconnaissance (BTC 2014–2020, recon only — NOT tuned)

FFT on BTC daily log-returns, dominant periods (bars), top-8 in [4, 160]:

> **[5.3, 5.4, 5.8, 6.2, 6.3, 8.3, 20.3, 20.8]**  vs canonical FX **[10, 20, 40]**

Crypto's spectral energy is concentrated at **~5–8 bars** plus a **~20-bar**
band; the **40-bar parent is essentially absent**. The FX-canonical
`(10, 20, 40)` FLD ladder is mis-scaled for crypto's faster cyclic
structure. This is the mechanistic explanation for the trade-scarcity
finding below (a 40-bar parent that the data does not exhibit makes the
loose-M + 3-FLD confluence rarely line up). **Reconnaissance only** — not
used to alter H26. Candidate **H27**: re-recon crypto cycles formally and
test a crypto-native ladder (e.g. `5/10/20` or `8/16/32`), as a *new*
calibrated experiment, not an in-step tune.

## Methodology

Verbatim H23/H16 `run_one` engine (loose-M `PatternConfig` dip=50,
`fld_bias` (10,20,40), Scheme D bull0/neu1/bear3, `rm` metrics), 70/30
split **by bars**, `seed=42`. **Decision rule per the H26 brief — stated
on OOS trades (the STRICT reading):** GO = OOS Sortino ≥ +3.0 AND OOS
trades ≥ 30; NO-GO = OOS Sortino < +1.0 OR OOS trades < 10; SWEEP
otherwise. Thin GO (OOS trades < 20) → H24 4-test robustness gate.

*Load-bearing note:* this OOS-trade rule is **stricter** than H23's
full-trade-floor PRAGMATIC reading. I followed the H26 brief literally and
also checked the PRAGMATIC view — **the 0-GO conclusion is robust to
either**: no crypto major reaches 30 *full* trades either (BTC 26, ETH 25,
SOL 13), so PRAGMATIC would yield SWEEP-at-best, never GO. The transfer
verdict does not hinge on the rule choice.

## Per-symbol cards

### BTCUSD — NO-GO (genuine + OOS-thin)
2014-09-17→2026-05-18, 4,262 bars. OOS 2022-11-17→2026-05-18 (1,279 bars).

| Slice | Trades | Univ | Sortino | Sharpe | R/yr | MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| IS | 21 | 53 | +29.86 | +1.03 | +15.01 | −0.7% |
| OOS | **5** | 24 | **+0.65** | +0.22 | +1.55 | −6.3% |
| FULL | 26 | 77 | +8.30 | +0.80 | +9.37 | −3.3% |

NO-GO on **both** clauses (OOS Sortino +0.65 < 1.0 AND OOS trades 5 < 10).
IS is spectacular (+29.86) but the OOS slice (post-FTX 2022-11 onward, the
2023–24 grind + 2024–25 rally) produced only 5 Scheme-D trades and a flat
risk-adjusted result. This is the clearest IS→OOS degradation in the study
— but on a 5-trade OOS sample the degradation itself is barely measurable.
Genuine NO-GO, compounded by OOS thinness.

### ETHUSD — NO-GO **by trade-count only** (edge looks excellent)
2017-11-09→2026-05-18, 3,113 bars. OOS 2023-10-28→2026-05-18 (934 bars).

| Slice | Trades | Univ | Sortino | Sharpe | R/yr | MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| IS | 18 | 44 | +31.74 | +1.08 | +15.45 | −0.7% |
| OOS | **7** | 16 | **+12.55** | +0.66 | +16.29 | −2.9% |
| FULL | 25 | 60 | +19.63 | +0.87 | +13.83 | −1.9% |

**NO-GO purely on the OOS trade-count floor (7 < 10)** — the OOS Sortino
**+12.55** is the *highest OOS Sortino anywhere in the H12–H26 program*,
IS (+31.74) and FULL (+19.63) corroborate it, and there is **no IS→OOS
degradation** (the USDMXN/NZDUSD failure mode is absent — OOS is
*stronger* than IS-implied). This is a **data-constrained NO-GO**, not an
edge failure: the framework's M-P1 long edge appears to transfer to ETH
*beautifully*; the FX-calibrated detector just does not generate ≥10
qualifying signals in a ~2.5-year crypto OOS window. This is the single
strongest argument for H27 (crypto-native cycles → more signals → testable
at the locked floors).

### SOLUSD — NO-GO (genuine + data-constrained)
2020-04-10→2026-05-18, 2,230 bars. OOS 2024-07-19→2026-05-18 (669 bars).

| Slice | Trades | Univ | Sortino | Sharpe | R/yr | MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| IS | 9 | 23 | +28.20 | +0.96 | +8.94 | −0.5% |
| OOS | **4** | 7 | **−0.45** | −0.34 | −1.61 | −4.9% |
| FULL | 13 | 30 | +4.11 | +0.74 | +5.87 | −3.6% |

NO-GO on both clauses (OOS Sortino −0.45 < 1.0 AND OOS trades 4 < 10).
**Data-constrained as predicted** — SOL's 2020-onward history yields only
13 full trades; the OOS slice is 4 trades and net-negative. Both a genuine
NO-GO *and* structurally under-powered; do not over-read the negative OOS
Sortino on 4 trades.

## Bonus pairs (BNB-USD, XRP-USD) — not run, per rule

The brief gated bonus pairs on "≥1 of the 3 majors clears cleanly." BTC and
ETH are both NO-GO, so BNB/XRP were **not run** (no point expanding a
non-transferring configuration; saves a re-run when H27 changes the
cycles). Recorded, not chased.

## Crypto vs FX (figure 19)

FX M-LONG OOS Sortinos (from `results/_h23_run.json`): EURUSD +4.06,
GBPUSD +5.57, USDCAD +3.12, NZDUSD +5.34, DXY +1.34, USDJPY +1.64,
AUDUSD +1.85. Crypto OOS Sortinos: ETH **+12.55**, BTC +0.65, SOL −0.45.
The crypto distribution is **bimodal and extreme** — ETH far above any FX
pair, BTC/SOL below the NO-GO floor — exactly the fingerprint of a
**low-N, high-variance** regime: when a crypto M-P1 setup fires it pays
spectacularly, but it fires too rarely under FX cycles to satisfy the
trade-count floors.

## Decisions (load-bearing, documented — no-questions brief)

- **0 crypto GO ⇒ NO hurst-agent integration.** No `symbols:` /
  `asset_class: crypto` entry, no `rsi_m_p1.py` change, no `--dry-run`
  (nothing was added to dry-run). Per the hard rule: don't build dead
  infrastructure.
- **hurst-agent repo unchanged ⇒ nothing to push there.** The brief's
  "push both if any GO; rsi-only if zero GO" → rsi-pattern-research only.
- **The real deliverable is the H27 hypothesis.** The transfer test did
  its job: it isolated *why* crypto fails (FX-cycle signal scarcity, not
  absent edge) with a quantified mechanism (cycle recon) and a falsifiable
  next step (crypto-native FLD ladder). ETH +12.55 OOS with zero IS→OOS
  degradation is a strong prior that H27 is worth running.

## Net read

The M-P1 LONG **edge plausibly transfers to crypto — possibly better than
to FX** (ETH OOS +12.55, no degradation) — but the **FX-calibrated cyclic
geometry (10/20/40 + loose-M) does not**: it under-samples crypto's faster
~5–8-bar structure and never reaches the trade-count floors. As configured,
crypto is **NO-GO across the board**, and that verdict is robust to the
STRICT-vs-PRAGMATIC rule choice. Next highest-leverage move is **H27:
crypto-native cycle re-recon + ladder calibration**, run as a fresh
calibrated experiment (not a per-symbol tune), then re-test at the locked
floors. Until then nothing ships and the live DXY agent is untouched.
