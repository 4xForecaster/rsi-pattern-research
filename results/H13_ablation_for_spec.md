# H13 — Ablation for Trading Spec (Resolving the 3 Discrepancies)

**Date:** 2026-05-12

Step 3 follow-up. Dr. A's call: resolve the three spec discrepancies
empirically by running a controlled ablation over Scheme D, then promote
the trading spec to v1.1 reflecting whichever variant wins on
risk-adjusted profitability.

## Knobs swept

| # | Knob | Baseline (current code) | Alternative |
|---|---|---|---|
| 1 | **Detector** | Loose-M (`patterns.detect_m`, peaks ≥65, dip ≥50, completes <50) | Strict-M (`patterns_strict.detect_strict_m`, origin <30, peaks ≥75.01, wiggle floor ≥70) |
| 2 | **Initial stop** | Structural-only: low of the 60-bar pre-P1 floor bar | Wider of structural OR `entry − 1×ATR(14)` — i.e., whichever sits *farther below entry* (looser stop = less whipsaw) |
| 3 | **Range anchor** | Pre-P1: `high(P1) − min(low) over [P1−60, P1)` | Pre-entry / M's inner trough: `high(P1) − min(low) over [P1, last_anchor]` (P2 for loose-M, last_major_peak for strict-M) |

All other Scheme D parameters held fixed: skip bullish FLD, 1× neutral, 3×
bearish; SURF Fib 1.618/2.236/3.618; trail at 3.600× range; 200-bar time
stop; 1% risk per 1× position; daily DXY 1990-01-02 → 2026-05-04.

## Cells run (5)

The three one-variable swaps from baseline + the all-three-on combination.

| Cell | Detector | Stop | Range |
|---|---|---|---|
| baseline | loose | structural | pre-P1 |
| v1 strict-M | **strict** | structural | pre-P1 |
| v2 wider ATR | loose | **wider-ATR** | pre-P1 |
| v3 pre-entry range | loose | structural | **pre-entry** |
| v_all | **strict** | **wider-ATR** | **pre-entry** |

## Results

| Cell | Trades | Mean R | Total R/yr | Sharpe | Sortino | Calmar | MAR | Max DD |
|---|---|---|---|---|---|---|---|---|
| **baseline (loose / struct / pre-P1)** | 56 | +4.15 | +6.78 | +0.47 | **+5.75** | -0.27 | +1.29 | -2.78% |
| v1 strict-M | **2** | +2.03 | +0.18 | +0.14 | +0.74 | -0.33 | +0.18 | -0.95% |
| v2 wider stop (ATR) | 56 | +3.53 | +5.78 | +0.50 | +4.77 | -0.27 | +1.05 | -3.08% |
| v3 pre-entry range | 56 | +7.29 | +11.99 | +0.37 | +3.79 | +9.41 | +0.76 | -6.45% |
| v_all (strict + wider + pre-entry) | **2** | +7.59 | +0.66 | +0.24 | n/a | n/a | n/a | 0.00% |

## Selection (per stated rule)

1. **Strict-M cells excluded.** v1 and v_all both yield only **2 trades**
   over 36 years of daily DXY — well below the 20-trade validity floor
   the user set. Strict-M was originally designed for higher-frequency
   timeframes (the SYNOPSIS shows it tested on 1h); on daily it screens
   out essentially all signal. Not a valid empirical test either way.

2. **Highest Sortino among valid cells**: baseline +5.75, v2 +4.77, v3 +3.79.
   Baseline leads by **+0.98 Sortino (17%)** over the runner-up — well
   outside the 5% tie threshold. **Tie-breakers do not apply.**

3. **Winner: baseline.** No changes to the v1.0 rules — the current code
   *is* the empirically best Scheme D configuration on daily DXY by
   downside-adjusted risk.

## Per-knob analysis

### Knob 1 — Detector (loose-M vs strict-M)

Strict-M produces only 2 trades on 36 years of daily DXY. The threshold
stack (RSI must rise from <30 to ≥75.01 with a wiggle floor of 70) is
calibrated for higher-frequency oscillations and almost never triggers
on daily bars. **Cannot be evaluated on this timeframe.** Strict-M
remains useful as a higher-quality screen on 1h/4h data (per the
synopsis figures) but is the wrong tool for daily DXY.

### Knob 2 — Initial stop (structural vs wider ATR)

Adding the `entry − 1×ATR(14)` floor only matters when ATR > structural
distance. When that happens, the wider stop reduces R-multiples on
winners proportionally (smaller R = same dollars but larger denominator)
without saving us many trades — Sharpe ticks up slightly (+0.47 → +0.50)
because mean and std move together, but Sortino drops (+5.75 → +4.77)
and Mean R drops (+4.15 → +3.53). The structural stops on this strategy
weren't being whipsawed enough to need ATR padding. **Stop stays
structural-only.**

### Knob 3 — Range definition (pre-P1 vs pre-entry / inner trough)

The most interesting cell. Pre-entry range uses the M's inner trough,
which is usually shallower than the rise-origin floor (60 bars back).
Smaller range → smaller stop distance → **bigger R on winners**: Mean R
jumps from +4.15 to +7.29, Total R/yr nearly doubles to +11.99. But the
tighter stop also produces bigger fractional losses on losers — Max DD
goes from −2.78% to **−6.45%**, and the loss tail widens enough that
Sortino drops to +3.79.

Curiously v3's *Calmar* is **+9.41**, by far the best of any cell —
its trailing 3-year window is the only one that's positive (concentrated
late-cycle winners). But Sortino is what the selection rule prioritizes,
and v3 underperforms baseline by 34% on that metric.

**Worth a follow-up**: v3 might be the right choice for a return-maxing
operator who is fine with 6.5% peak DD. Under the Sortino-primary rule,
it doesn't qualify. Flagging for a possible Scheme F variant in a future
hardening step.

## Decision

**Baseline wins on Sortino. Spec promoted to v1.1 with no rule changes
— the version bump records that the three discrepancies were tested
empirically and the current code was the right choice.**

The 3 discrepancies between Dr. A's original Step-3 draft and the code
are therefore reconciled as follows:

| # | Draft suggestion | v1.1 ruling | Why |
|---|---|---|---|
| 1 | Use strict-M | **Keep loose-M** | Strict-M produces 2 trades on daily DXY (below 20-trade floor); empirically untestable, not better. |
| 2 | Add ATR-based stop floor | **Keep structural-only** | ATR floor costs +0.98 Sortino and −0.62 Mean R for no DD improvement. |
| 3 | Use pre-entry range | **Keep pre-P1 range** | Pre-entry boosts Mean R but loses Sortino (5.75 → 3.79) and triples Max DD. Flagged for possible Scheme F. |

## Code

- Ablation script: [`scripts/h13_ablation_for_spec.py`](../scripts/h13_ablation_for_spec.py)
- Reproducible: `python3 scripts/h13_ablation_for_spec.py`
