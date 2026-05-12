# H22 — V-floor-breach Short, Full Backtest + Walk-Forward

**Date:** 2026-05-12

H10 identified V-floor breach as the **largest single signal** in the
RSI pattern system — Cohen's d ≈ −1.53 on daily DXY (20-bar forward
return). The function `fib_short_at_v_floor` has existed in
`position_sizing.py` since H7 but was never run through the Scheme G
framework or the H12 risk-adjusted metric stack.

H21 found the symmetric V-T1 short was a null (FLD-skew at deep
oversold). V-floor breach is a different signal — **continuation**
after the V fails to hold (RSI breaks below the V's own floor), not
**reversal** at first trough. The entry happens later, after the
V completes, giving more time for FLD divergence to emerge.

**Result: third null in a row.** Has signal 1990-2015, decays
to negative Sortino post-2015. Cohen's d on directional moves does
NOT translate to a SURF-Fib-trade positive R-multiple distribution
that holds up out-of-sample.

## TL;DR

| Phase | Window | Trades | Mean R | Sharpe | **Sortino** | Max DD |
|---|---|---:|---:|---:|---:|---:|
| Phase 1 (full) | 1990-01 → 2026-05 (36.3y) | 63 | +0.55 | +0.24 | **+0.72** | −7.14% |
| Phase 2 train | 1990-01 → 2015-07 (25.5y) | 44 | +0.91 | +0.34 | **+1.16** | −7.14% |
| Phase 2 test | 2015-07 → 2026-05 (10.8y) | 18 | −0.08 | −0.06 | **−0.10** | −4.29% |

**Phase 2 verdict: PAPER_FIT** (test/train ratio −0.08 < 0.33).
Production decision: **NOT VIABLE.** Fails Sortino, mean-R, and
generalization gates.

## Setup

- **Data:** daily DXY, 9,304 bars, 1990-01-02 → 2026-05-04 (36.3 yrs)
- **Detector:** loose-V (`patterns.detect_v`, default cfg: troughs ≤35,
  inner peak ≤50, completion ≥50)
- **Entry rule:** breach+1 — first bar after V completion where RSI
  drops below `min(rsi[T1], rsi[T2])`, then enter SHORT at the
  following close
- **Range:** `define_fib_range_short` — high(60-bar pre-breach window)
  minus low(V's floor or breach bar)
- **Initial stop:** above entry at the range high
- **Targets:** entry − 1.618 / 2.236 / 3.618 × range
- **FLD bias:** cycles (10, 20, 40), bullish = price > all 3, bearish
  = price < all 3
- **Scheme G adapted for shorts:** bullish FLD is the "high-conviction"
  bucket (price overextended above all 3 FLDs = mean-reversion-down
  setup)

## Phase 1 — Full-window 5-scheme sweep

| Scheme | Trades | Mean R | Total R/yr | Sharpe | Sortino | Max DD | Bias (B/N/b) |
|---|---:|---:|---:|---:|---:|---:|---|
| A. Pure parallel (1/1/1) | 63 | +0.48 | +0.87 | +0.23 | +0.70 | −5.88% | 4 / 20 / 39 |
| **B. Modest (3/1/1)** | **63** | **+0.55** | **+1.01** | **+0.24** | **+0.72** | **−7.14%** | 4 / 20 / 39 |
| C. Aggressive (5/1/1) | 63 | +0.63 | +1.15 | +0.23 | +0.69 | −8.23% | 4 / 20 / 39 |
| D. Skip bearish + 3× bullish | 24 | +0.86 | +0.60 | +0.17 | +0.54 | −6.95% | 4 / 20 / 39 |
| E. Conservative (3/1/0.5) | 63 | +0.44 | +0.80 | +0.21 | +0.66 | −6.19% | 4 / 20 / 39 |

**Phase 1 winner: Scheme B** by a hair (+0.72 Sortino, +0.03 over A
and C). All schemes cluster within 0.18 Sortino — the FLD-bias scaling
adds essentially nothing on this signal.

Note the **bias distribution (4/20/39) is much more balanced than
H21's V-T1 entry (0/12/51).** H21's structural argument
("FLD-skew dooms shorts at deep oversold") was specific to first-
trough entries. By the time a V completes AND breaches its own floor,
some FLD divergence has had time to develop — 4 of 63 entries are
bullish-FLD. Still rare though.

## Phase 2 — Walk-forward 70/30 on the winner

| Slice | Window | Trades | Mean R | Sharpe | Sortino | Max DD |
|---|---|---:|---:|---:|---:|---:|
| Train | 1990-01-02 → 2015-07-22 (25.5y) | 44 | +0.91 | +0.34 | **+1.16** | −7.14% |
| Test  | 2015-07-23 → 2026-05-04 (10.8y) | 18 | −0.08 | −0.06 | **−0.10** | −4.29% |

Test/train Sortino ratio: **−0.08** → **PAPER_FIT**.

The signal had real edge 1990-2015 (Sortino +1.16 with 44 trades) and
then **died** post-2015. Possible causes (cannot disambiguate from one
split):

1. **2015 SNB shock** — January 2015 EUR/CHF removal of the floor was
   a regime-defining event. The data after has a structurally
   different FX volatility profile.
2. **Post-2015 central-bank intervention** — QE-era policy converged
   FX vol; sharp V-pattern flushes became rarer or less reliable.
3. **DXY trended persistently after 2014** — strong USD bull market
   2014-2016, then range-bound. V-floor-breach shorts entered into a
   structurally rising DXY likely got stopped repeatedly.
4. **Pure noise** — 18 test trades has wide confidence intervals;
   the Sortino −0.10 isn't strongly negative, just zero-ish.

## Cohen's d vs SURF Fib R-multiple

H10's effect-size table showed V-floor breach with d = −1.53
(very large negative effect) on daily DXY. H22 finds Mean R +0.55
on the same data. These aren't contradictory — they measure different
things:

- **Cohen's d on 20-bar forward return:** is the average price 20
  bars after the signal lower than baseline? Answer: yes, by a large
  margin (d = −1.53).
- **SURF Fib R-multiple:** does the specific structure of
  entry-at-breach+1 / stop-above / targets-at-1.618/2.236/3.618×range
  / trail-at-3.6× produce positive expected payoff? Answer: yes
  weakly (mean R +0.55), but not robustly OOS.

**The H10 effect size is a real property of the underlying
price dynamics.** What's missing is that SURF Fib's stop placement
(at the pre-breach high, often a wide stop) gives back enough R per
loss to neutralize the directional edge. A tighter-stop variant might
extract more of the d = −1.53 — but that's a different strategy
architecture, not a parameter tweak.

## Implications for the overall strategy

This is the **third short-side / variant null in a row**:
- H20: 1h timeframe — NOT VIABLE (production gates failed)
- H21: V-T1 short mirror — NULL (FLD-skew structural)
- **H22: V-floor breach short — PAPER_FIT** (signal real but doesn't
  generalize OOS)

**Honest read: the strategy's edge is concentrated in
long-side M-P1 with FLD-bearish scaling.** The remaining H21 alternatives
(FLD slope/divergence, trend filter, C→V 1-bar signal) are speculative
and unlikely to add edge given the three nulls already documented.

The production strategy stands at:
- Long-only M-P1 with Scheme C (5× bearish-FLD)
- Expected OOS Sortino: +2 to +4 (regime-dependent, per H19)
- Scheduling: launchd installer ready, awaiting Dr. A's TCC remediation
- Telegram wiring: complete, awaiting live creds verification

## What I'm NOT doing next

- Not pursuing H21 alternatives #1 (FLD slope), #3 (trend filter),
  or #4 (C→V 1-bar signal). Three nulls in a row suggests the
  short-side bag is empty under the SURF Fib structure. Could
  revisit with a tight-stop variant (e.g., entry +1×ATR stop) but
  that's a different research arc, not a quick win.
- Not pursuing tighter-stop V-floor breach as a quick variant — the
  effect-size-to-R-multiple gap is interesting but the post-2015
  regime change is the bigger issue.
- Not pursuing pre-2015-only V-floor breach — would require live
  regime-shift detection to know when the strategy is back in
  season. Out of scope.

## What's actually worth doing next

In priority order:
1. **Exit-side lifecycle alerts (D from earlier menus)** — entries
   already fire (post-TCC fix); traders need T3_hit, trail_armed,
   stopped_out events to manage positions. Operational, finite scope.
2. **Telegram live-creds verification (E)** — manual step on
   Dr. A's machine. Confirms the wire works end-to-end with real
   credentials.
3. **Live-signal monitoring dashboard** — `state/audit.jsonl` has
   the audit trail; a small HTML viewer or `make rsi-mp1-status`
   that prints "last regime label, N signals fired this week, last
   transition timestamp" would close the operational loop.

## Code

- Runner: [`scripts/h22_v_floor_breach_short.py`](../scripts/h22_v_floor_breach_short.py)
- Figure: [`figures/11_h22_v_floor_short.png`](../figures/11_h22_v_floor_short.png)
- Raw JSON: `results/_h22_run.json`
- Underlying trade engine: `position_sizing.fib_short_at_v_floor`
  (existed since H7; never wrapped in Scheme G framework before H22)
