# H25 — V-Pattern SHORT Cross-Symbol Expansion (Negative Result)

**Date:** 2026-05-19
**Module:** [`src/rsi_pattern/strategies_vshort.py`](../src/rsi_pattern/strategies_vshort.py)
**Script:** [`scripts/h25_vshort_expansion.py`](../scripts/h25_vshort_expansion.py)
**Unit test:** [`tests/test_vshort_symmetry.py`](../tests/test_vshort_symmetry.py) — 12/12 pass
**Run dump:** [`results/_h25_run.json`](_h25_run.json)
**Figures:** [`figures/16_vshort_equity_curves.png`](../figures/16_vshort_equity_curves.png),
[`figures/17_mlong_vs_vshort_matrix.png`](../figures/17_mlong_vs_vshort_matrix.png)

## TL;DR

**The V-floor-breach SHORT signal does not transfer to any pair. Zero
GOs across the 9-pair universe. The hypothesis is falsified.**

The premise was: M-P1 LONG fails (structurally) where a pair trends
*down*, so a symmetric V-SHORT should harvest those inverse
opportunities and flip structural NO-GO/SWEEP pairs into new GOs. It does
not. The supposed beneficiaries are the *worst* V-SHORT performers
(AUDUSD OOS Sortino **−2.76**, NZDUSD −0.26, USDMXN +0.54). Per the hard
rule, **no hurst-agent integration is built** — this documents the
negative result instead of shipping dead infrastructure.

## Faithfulness gate (ran first, before any expansion)

`strategies_vshort` reuses the already-H8-tested
`position_sizing.fib_short_at_v_floor` engine rather than re-deriving the
short mechanics, so faithfulness is structural. Confirmed empirically:

> DXY daily V-floor SHORT mean R-multiple = **+0.4766** vs H8 anchor
> **+0.48** (±0.05). **PASS — faithful.**

The expansion proceeds on a faithful implementation, not a broken one.

### Symmetry unit test (the asymmetry-prone part)

The 3-bar trailing stop + inside-bar exclusion is where a subtle
long-vs-short asymmetry would hide. `tests/test_vshort_symmetry.py`
pins the invariant: reflecting price through zero turns the long-side
trailing stop into the negated short-side stop, bar-for-bar, **including
the inside-bar skip and the no-fill sentinels** (long → −inf,
short → +inf). 12/12 parametrized cases pass. The V-SHORT pipeline is a
faithful mirror of M-LONG; cross-direction comparison is valid.

## Methodology (identical protocol to H23/H24 — no re-tune)

- Detector: `patterns.detect_v` on RSI-14, default `PatternConfig`
  (same config family the M side uses). No per-pair tuning.
- Entry: SHORT at close of the bar after RSI breaks the lower V-trough.
- Range: V-high − V-floor. Targets: SURF Fib 1.618/2.236/3.618× *below*
  entry. Trail: 3-bar, arms at 3.600×, mirror inside-bar rule.
- Sizing: Scheme D read at the SHORT entry bar. Per the brief: bullish
  FLD = wrong direction → skip (0×), neutral → 1×, bearish (favorable
  for a short) → 3×. This is the tuple `(bullish 0, neutral 1,
  bearish 3)` — numerically identical to the M-LONG tuple. That
  coincidence is expected: in both directions the favorable-confirmation
  bucket is sized 3× and the contrary bucket is skipped. Not a bug.
- 70/30 split by bars; OOS Sortino load-bearing; full-sample 30-trade
  floor. Locked rule: GO = OOS Sortino ≥ +3.0 AND full trades ≥ 30;
  NO-GO = OOS Sortino < +1.0 OR full trades < 10; else SWEEP. Any thin
  V-SHORT GO (OOS n < 15) gets the full H24 4-test robustness pass
  (bootstrap N=10,000 `seed=42`, rolling 4×50%-span, Gini ≤ 0.7,
  per-trade drop-one ≥ +2.5).
- 9 pairs. DXY = BarChart daily (reproduces H8). FX = yfinance, cached
  keyed by ticker (USDMXN `MXN=X`, USDCHF `CHF=X` — H15 continuity).
  No symbols skipped; all caches clean.

## Per-pair V-SHORT result + directional comparison

| Symbol | M-LONG | V-SHORT | M OOS Sortino | V OOS Sortino | V OOS n / full | Quadrant |
|---|---|---|---:|---:|---|---|
| DXY | SWEEP | **NO-GO** | +1.34 | +0.10 | 18/59 | NEITHER |
| EURUSD | GO | **SWEEP**¹ | +4.07 | +4.26 | 13/34 | LONG-ONLY |
| GBPUSD | GO | **SWEEP** | +5.57 | +2.24 | 11/19 | LONG-ONLY |
| USDJPY | SWEEP | **SWEEP** | +1.64 | +2.44 | 9/41 | NEITHER |
| USDCAD | GO | **NO-GO** | +3.12 | +0.38 | 13/40 | LONG-ONLY |
| AUDUSD | SWEEP | **NO-GO** | +1.85 | −2.76 | 4/26 | NEITHER |
| NZDUSD | GO | **NO-GO** | +5.34 | −0.26 | 12/29 | LONG-ONLY |
| USDMXN | SWEEP | **NO-GO** | +2.53 | +0.54 | 21/50 | NEITHER |
| USDCHF | SWEEP | **NO-GO** | +2.43 | +0.48 | 12/41 | NEITHER |

¹ **EURUSD V-SHORT was GO by the locked mechanical rule** (OOS Sortino
+4.26 ≥ 3.0, full 34 ≥ 30) **but failed the H24 robustness gate 1/4 →
downgraded to SWEEP.** Detail: bootstrap p5 +0.60 (< +3.0, fail),
rolling `[8.56, 6.58, 0.48, −0.88]` = 2/4 (fail ≥3/4), Gini **0.921**
(> 0.7 → cluster-dependent, fail), per-trade min +2.87 (pass). This is
the *same* failure shape the gate caught for NZDUSD M-LONG in H24 — the
+4.26 headline is one profit cluster (2019–2023 windows), not a
stationary edge. The robustness gate generalizes across both directions;
without it EURUSD V-SHORT would have been a spurious GO.

### Quadrant tally

- **LONG-ONLY** (M GO, V not-GO): EURUSD, GBPUSD, USDCAD, NZDUSD — 4
- **NEITHER**: DXY, USDJPY, AUDUSD, USDMXN, USDCHF — 5
- **SHORT-ONLY**: **0**
- **BOTH**: **0**

## Why the hypothesis failed (structural read)

1. **No pair is SHORT-ONLY or BOTH.** The directional-inverse premise
   predicted that pairs where M-LONG fails for "wrong direction" reasons
   (AUDUSD, USDCHF, USDMXN) would flip to V-SHORT GO. They are instead
   **NEITHER** — V-SHORT is *also* weak-to-negative there. AUDUSD is the
   sharpest refutation: M-LONG SWEEP *and* V-SHORT actively loses (OOS
   −2.76). The opportunity is not "on the other side"; it is not there
   in this signal formulation.

2. **The "M NO-GO → V GO" cell is structurally empty.** Under the strict
   70/30 protocol no pair is M-LONG NO-GO (worst M is SWEEP). The
   inverse-flip cell the hypothesis lived in does not even get populated,
   and the M-SWEEP pairs do not flip either. The hypothesis is dead for
   this V-floor-breach formulation.

3. **V-floor breach is a weak continuation signal even at the source.**
   H8 already showed DXY V-SHORT mean R only +0.48 with a 22% T1-hit
   rate and 38% stop-out — false breakdowns (price snapping back through
   the floor) eat the edge. H25 confirms that weakness is *general*, not
   DXY-specific. The M-top long entry has a real asymmetric-payoff edge
   on USD-trend-up pairs; its V-floor mirror does not have a symmetric
   edge on USD-trend-down pairs.

## Decisions (load-bearing, documented per the no-questions brief)

- **No hurst-agent integration.** 0 V-SHORT GO ⇒ per the hard rule
  ("integration only if ≥1 GO; don't build dead infrastructure"), no
  `v_short_symbols:` block, no `strategies/v_short.py`. The negative
  result is the deliverable.
- **No schema bump.** A `schema_version` bump to 2 would have *crashed
  the live DXY cron* — `hurst_agent/strategies/rsi_m_p1.py` hard-asserts
  `schema_version == 1` and raises otherwise. Even had there been GO
  pairs, a new top-level `v_short_symbols:` block is purely additive and
  ignored by the live loader, so no bump would have been needed. With
  zero GOs the question is moot; recorded so a future agent does not
  bump it reflexively.
- **hurst-agent repo unchanged ⇒ nothing to commit/push there.** "Push
  both repos" was conditioned on the integration the brief itself gates
  on ≥1 GO. Pushing an empty change would be noise.
- **`strategies_vshort.py` is kept** (committed to rsi-pattern-research)
  even though it found no GO: it is a faithful, unit-tested research
  asset and the engine behind this negative result. Keeping it makes the
  negative reproducible; it adds no runtime surface to the live agent.

## Net read

The framework is **directionally asymmetric by nature, not by
calibration**. The M-P1 LONG edge is real on USD/base-trend-up majors
(EURUSD, GBPUSD, USDCAD solid; see H23/H24). Its V-floor-breach SHORT
mirror has no symmetric counterpart edge anywhere in the 9-pair
universe. Future short-side work should not retry V-floor breach with
tweaked knobs (out of scope, and H8+H25 jointly say the signal itself is
weak) — it needs a *different* short trigger or a regime/trend overlay,
which is a separate experiment, not an H25 re-tune.
