# H29 — Box-Pattern Signal: Detect, Backtest, Confluence (Negative)

**Date:** 2026-06-18
**Module:** [`src/rsi_pattern/box_pattern.py`](../src/rsi_pattern/box_pattern.py)
**Unit tests:** [`tests/test_box_pattern.py`](../tests/test_box_pattern.py) — 5/5 pass
**Script:** [`scripts/h29_box_pattern_validation.py`](../scripts/h29_box_pattern_validation.py)
**Run dump:** [`results/_h29_run.json`](_h29_run.json)
**Figures:** [`figures/24_box_pattern_example.png`](../figures/24_box_pattern_example.png),
[`figures/25_box_cross_symbol_sortinos.png`](../figures/25_box_cross_symbol_sortinos.png)

## TL;DR — 0/7 GO. The spec detects cleanly; the *bias rule* doesn't predict.

The 4-point box detector (P0 swing low → P1 swing high → P2 50%-retrace
touch → P3 break of P1) is implemented and passes both the unit-test
synthetic fixtures (5/5) and an inline DXY mechanics audit (5/5 sampled
boxes verified for ordering, 50% touch, P3 break, and asymmetry sign).
**Detection is faithful.**

The Hurst time-asymmetry filter (take a LONG only when P1.idx > T-mid)
is faithfully implemented as written — and it **does not produce a
tradeable edge** on any of the 7 FX symbols at the locked thresholds.
Aligned-and-traded boxes cluster between OOS Sortino −1.65 and −0.46
(median ≈ −0.5). No hurst-agent change.

## Faithfulness gate (ran first)

| Check | Result |
|---|---|
| Unit tests (synthetic LONG bull, LONG bear-skip, SHORT mirror, dedup, structural-stop) | **5/5** |
| DXY: long boxes found | **34** |
| DXY: short boxes found | **67** |
| DXY: sampled boxes (first 5) — all four mechanics OK | **5/5** |

Resolved-ambiguity choices live in `box_pattern.py`'s header docstring
(swing prominence is *price-normalized* — 0.5% of close — because the
spec'd "same prominence as the M-detector" reads 3.0 in RSI units and is
degenerate on price; distance=3 bars is preserved). All other rules
implemented verbatim.

## Per-pair backtest (70/30, OOS load-bearing, no per-symbol tuning)

| Symbol | Univ | Aligned | Trades | OOS trades | OOS Sortino | Full Sortino | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| DXY    | 34 |  6 |  5 |  3 | −0.46 | −0.12 | NO-GO |
| EURUSD | 51 |  5 |  4 |  0 |  n/a  | +0.78 | NO-GO (OOS n=0) |
| GBPUSD | 51 |  7 |  7 |  2 | −1.21 | −0.47 | NO-GO |
| USDJPY | 24 |  2 |  2 |  2 | −0.76 | +0.54 | NO-GO |
| USDCAD | 20 |  2 |  2 |  4 | +0.43 | −0.26 | NO-GO |
| AUDUSD | 87 | 11 | 11 |  6 | −0.19 | −0.14 | NO-GO |
| NZDUSD | 83 | 14 | 14 |  6 | −1.65 | −0.60 | NO-GO |

**0 GO.** Every pair fails both the OOS Sortino floor (< +1.0) and the
trade-count floor (< 10). The result is robust to the rule choice
(STRICT vs PRAGMATIC) and to the cadence: even the symbols with healthy
universes (AUDUSD 87, NZDUSD 83) collapse to ≤14 aligned trades, and
those trades carry negative Sortino.

**The bias filter is the choke point.** Universes are healthy (24–87
boxes per pair) but the time-asymmetry rule passes only ~10–18% of them.
Without that filter you would have many more boxes — and the filter is
*spec'd* (rule #7) so removing it isn't an in-step option.

## Why aligned-and-traded fails: a falsifiable next-step hypothesis

The locked rule says "P1.idx > T-mid → rally took longer than correction
→ bullish trend bias (trade the long)." The data on these 7 symbols says
that condition does **not** predict subsequent uptrends — if anything it
mildly *under-performs* (median Sortino across pairs ≈ −0.5).

A plausible alternative reading worth a *new* experiment (NOT here — H29
is a benchmark of the spec, not a tuner): "fast rally + slow correction"
(P1.idx < T-mid) might mark trend exhaustion or *bullish* re-accumulation
contexts. H30 candidate: re-run the same harness with the bias rule
inverted (LONG box + P1.idx < T-mid → trade) as a pre-registered single
test, and abandon the inversion if it doesn't clear ≥2/7 pairs to GO
under the locked floors. This is a hypothesis, not a finding — H29 ships
the **negative on the spec as written**.

## Confluence with M-P1 LONG: 0% overlap

For every symbol, box-LONG entry dates and M-P1 LONG entry dates have
**zero intersection** on the full sample (`overlap_pct_min = 0%`). The
two signals are **orthogonal** — they fire on completely different bars.
Per the H29 hard rule (confluence ships only if both signals are GO
independently *and* confluence improves), no confluence strategy is
backtested or shipped: box is 0/7 GO. The orthogonality is itself a
useful prior — if the box rule were ever revived (e.g., post-H30), the
confluence question would be live for the first time, because right now
the bars don't overlap at all.

## Decisions (load-bearing, autonomous, no questions)

- **No hurst-agent integration.** 0 GO under the locked rule → no
  config entry, no `strategies/box_pattern.py` in hurst-agent, no
  `v_box_symbols:` block. Per the standing rule: don't build dead
  infrastructure.
- **No schema bump.** Same reasoning as H25 — and moot at 0 GO.
- **`src/rsi_pattern/box_pattern.py` is kept** as a faithful, unit-tested
  research asset (5/5 tests + DXY mechanics audit). It adds no runtime
  surface to the live agent; future agents (H30 inverted-bias, deeper
  sensitivity, swing-prominence sweep) can build on it without
  re-deriving the detector.
- **rsi-pattern-research push only.** Live DXY cron untouched.

## Net read

The box detector is correct and the spec was honored to the letter. The
data on 7 FX majors says the time-asymmetry rule as written does not
produce a tradeable directional bias at the locked thresholds. The most
specific positive contribution of this negative is the **orthogonality
finding** (box-LONG ⊥ M-P1 LONG: 0 same-day overlap), which would matter
the moment any reformulation of the box rule produces a positive edge.
Until then, nothing ships and the live agent is unchanged.
