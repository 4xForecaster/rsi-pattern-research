# H21 — Short-Side V-Pattern, First Pass

**Date:** 2026-05-12 (late afternoon)

H20 found Scheme A (no FLD scaling) outperforming Scheme C on 1h test
data. That hinted the long-side bearish-FLD amplifier is weakening.
The natural next move: build the symmetric **short-side** variant and
see if a parallel edge exists.

**Result: clean null.** The symmetric short does NOT transfer. Mean R
≈ 0; Sortino −2.79; the high-conviction FLD bucket is **structurally
empty** (0 trades). The mirror approach fails for a real architectural
reason, not bad luck — and that reason is informative for what would
actually work.

## What was built

| Component | Long side (H14) | Short side (H21, this commit) |
|---|---|---|
| Pattern detector | `detect_strict_m` | `detect_strict_v` (new) |
| Topology | rise <30 → peaks ≥72 → wiggle ≥72 → fall <50 | fall >70 → troughs ≤28 → wiggle ≤28 → rise >50 |
| Trade engine | `fib_long_at_p1` | `fib_short_at_v_t1` (new) |
| Entry | close of P1+1 (long) | close of T1+1 (short) |
| Range anchor | `high(P1) − min(low) over [P1−160, P1)` | `high(160-bar pre-T1 window) − low(T1)` |
| Initial stop | structural low (below entry) | structural high (above entry) |
| Targets | entry + 1.618/2.236/3.618 × range (up) | entry − 1.618/2.236/3.618 × range (down) |
| FLD high-conviction bucket | bearish FLD (price below all 3 FLDs) | bullish FLD (price above all 3 FLDs) |

Implementation: `detect_strict_v` inverts the RSI series
(`100 − rsi`) and reuses the strict-M detector, mapping thresholds
arithmetically (origin 70 ≡ 100−30, trough 28 ≡ 100−72, etc.). Math
is symmetric by construction. Risk-metrics `build_equity_curve_mtm`
gained short-side MTM support in this commit (33/33 RSI M-P1 tests
still pass).

## Backtest setup

Identical to H14 except direction-flipped:

- Data: 5m DXY, 19,999 bars, 2026-01-28 → 2026-05-12
- Strict-V thresholds: (70, 28, 28) — mirror of H14's (30, 72, 72)
- FLD cycles: (40, 80, 160); lookback 160; time stop 160; spread 3 bps
- 5-scheme sweep with short-side scaling (bullish_FLD is the "5×"
  bucket for shorts, mirroring bearish for longs)

## Results

| Scheme | Trades | Mean R | Sortino | Max DD | Bias counts (B/N/b) |
|---|---:|---:|---:|---:|---|
| A. Pure parallel (1/1/1) | 63 | +0.02 | −2.79 | −16.97% | 0 / 12 / 51 |
| B. Modest (3/1/1) | 63 | +0.02 | −2.79 | −16.97% | 0 / 12 / 51 |
| C. Aggressive (5/1/1) | 63 | +0.02 | −2.79 | −16.97% | 0 / 12 / 51 |
| D. Skip bearish + 3× bullish | 12 | −0.11 | −3.05 | −6.38% | 0 / 12 / 51 |
| E. Conservative (3/1/0.5) | 63 | −0.00 | −3.32 | −11.52% | 0 / 12 / 51 |

**A/B/C produce identical results** because there are **zero
bullish-FLD trades**. The 5× boost on a bucket of size 0 changes
nothing.

Mean R is essentially zero across all schemes. Schemes that try to
filter (D drops the dominant bearish bucket) produce fewer trades
and worse Sortino.

## Why it doesn't work (structural)

The long-side strategy succeeded for a non-obvious reason. Look at
the FLD bias distribution at each entry type:

| Pattern | Entry | Expected FLD bias | Why |
|---|---|---|---|
| M-P1 LONG | P1+1 (RSI ≥72, peak) | bullish (price > FLDs) | RSI is overbought → price has rallied → price > slow median FLDs |
| | rare case: bearish | bearish (price < FLDs) | Price overshot RSI's recovery — divergence; this was the H14 5× bucket |
| V-T1 SHORT | T1+1 (RSI ≤28, trough) | bearish (price < FLDs) | RSI is oversold → price has fallen → price < slow median FLDs |
| | rare case: bullish | bullish (price > FLDs) | Would require RSI to oversold while price is still above the slow FLDs — possible only at a sudden flush from very high |

In H14, **16 of 124 long M-P1 entries had bearish FLD bias** (13%).
That rare-but-present bucket carried the strategy's edge — the 5×
amplifier had something to amplify.

In H21, **0 of 63 short V-T1 entries had bullish FLD bias** (0%).
The mirror bucket isn't rare; it's effectively impossible on this
sample.

**This is not a sample-size issue.** It's a structural property of
the FLD calculation:
- FLDs are slow rolling medians shifted forward
- At a V trough (deep oversold), price has been falling for a while
- The 40/80/160-bar FLDs lag price; they sit ABOVE current price
- So bearish FLD bias (all 3 above price) is mechanically expected
  near every V

The same asymmetry runs the long side, but with a sign-flip:
- At an M peak, FLDs sit BELOW current price → bullish bias is the norm
- The exceptions (bearish bias at an M peak) require price to have
  fallen below the slow FLDs DESPITE RSI being at a peak — a real
  divergence signal
- That divergence is what H14's bearish-FLD 5× was capturing

The short-side mirror has no equivalent divergence. **There's no
"price above FLDs while RSI is at a trough" scenario** that the
strategy can hold out for.

## What this rules out — and what to try instead

### Ruled out

- ❌ Symmetric short-side mirror with FLD-bias scaling as designed.
  The architectural assumption (rare FLD bucket carries high
  conviction) doesn't apply mirrored.
- ❌ Using the existing `fib_short_at_v_floor` (V-floor breach
  CONTINUATION short) with the same Scheme G logic — it'd hit the
  same FLD-skew wall.

### Worth trying instead (not in scope here)

1. **Different FLD logic for shorts.** Instead of "all 3 FLDs above
   price = bullish" (which never happens at V troughs), use FLD
   **slope/divergence** signals:
   - "Slow FLD turning up while price still falling" → bullish reversal
   - "Short FLD breaks above mid FLD" → momentum-shift signal
2. **Asymmetric setups.** Pair `fib_long_at_p1` (M-P1) for longs with
   `fib_short_at_v_floor` (V-floor breach) for shorts. Different
   trigger semantics (reversal vs continuation) but both have
   well-defined FLD-bias structure.
3. **Trend filter instead of FLD scaling.** Drop the FLD-bias 5×
   multiplier for shorts; gate shorts on a multi-day downtrend
   (e.g., 50-day MA slope) instead. Sizes are uniform; selectivity
   comes from regime.
4. **Cross-pattern signal.** H10 found "C → V 1-bar" had a positive
   short-side effect size (-0.81 to -0.86 Cohen's d). Re-examine
   that as a short trigger — never made it into the trade-engine.

## Implications for the hurst-agent integration

No changes. The `rsi_m_p1` strategy module in hurst-agent emits
long-only signals; that stays the case. **Don't add a short-side
module based on this approach.** If a future variant (one of the
4 options above) materializes, it gets its own strategy module.

## What landed in this commit

| File | Change |
|---|---|
| `src/rsi_pattern/patterns_strict_v.py` (new) | `detect_strict_v` via inverted-RSI reuse of `detect_strict_m` |
| `src/rsi_pattern/position_sizing.py` | new `define_fib_range_short_pre_t1` + `fib_short_at_v_t1`; existing `fib_short_at_v_floor` untouched |
| `src/rsi_pattern/risk_metrics.py` | `build_equity_curve_mtm` now supports short trades (units, MTM, realized PnL all sign-correct) |
| `scripts/h21_short_side_first_pass.py` (new) | runs the 5-scheme sweep on full 5m window |
| `results/_h21_run.json` (new) | raw output |
| `results/H21_short_side_first_pass.md` (this file) | writeup |

H22 would have been the walk-forward extension if H21 had shown
positive signal. **Not pursuing.** The 4 alternatives above are
viable research tracks but each is a different strategy
architecture, not a parameter variation.

## Caveats

1. **104 days is one window.** It's possible the mirror works on a
   longer horizon with different regime mix. But the structural
   FLD-skew argument is independent of window — the 0% bullish-FLD
   count is a *property of the indicator at this pattern type*,
   not a coincidence on this sample. Wouldn't expect it to change
   meaningfully on more data.
2. **Strict-V thresholds were inherited from H14's strict-M with
   no calibration.** A short-specific grid sweep might find better
   thresholds. But the +0.02 Mean R says the underlying setup has
   no edge to find; threshold tweaks won't fix that.
3. **5m is the wrong timeframe for V-trough reversals** — these
   tend to develop over hours/days. Trying on 1h or daily might
   give different numbers, but the FLD-skew structural argument
   applies on all timeframes.

## Code

- Strict-V detector: `src/rsi_pattern/patterns_strict_v.py`
- Trade engine: `src/rsi_pattern/position_sizing.py::fib_short_at_v_t1`
- Backtest runner: `scripts/h21_short_side_first_pass.py`
- Reproducible: `python3 scripts/h21_short_side_first_pass.py`
