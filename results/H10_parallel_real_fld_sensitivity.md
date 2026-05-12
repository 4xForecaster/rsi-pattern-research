# H10 — Parallel positions + Real Hurst FLD + Sensitivity sweep

**Date:** 2026-05-12

Three independent workstreams to harden the LONG @ P1 system.

## 1. Parallel-position equity curve

Removed the one-position-at-a-time cap. All 124 trades captured.

| Variant | Trades | Cumulative R | Annualized R | Max DD | Max Concurrent |
|---|---|---|---|---|---|
| Sequential (1-pos) | 37 | +70.6 | +1.94/yr | -2.0 R | 1 |
| **Parallel (no cap)** | **124** | **+153.8** | **+4.23/yr** | **-7.6 R** | **8** |
| FLD-bearish-only (parallel) | 16 | +64.5 | +1.78/yr | -2.0 R | ~3 |

**Parallel implementation captures 2.2× the return** by trading all overlap signals. Max concurrent positions of 8 means you need capital sized for 8× single-position exposure. At 1% risk per trade, that's up to 8% concurrent risk.

Max drawdown of -7.6R = -7.6% capital peak-to-trough over 36 years. Still very manageable for a +4.23%/year strategy.

## 2. Real Hurst FLD confluence — BIG FINDING

Used the **canonical Hurst FLD spec** from `~/Documents/4xForecaster/hurst-agent/src/hurst_agent/cycles.py`:
- Daily periods: **signal=10, mid=20, sequence=40** (NOT the 40/80/120 I tested earlier)
- Source = (high + low) / 2
- Shift = **period // 2 + 1** (not just period / 2)

Confluence with M-P1 LONG entries shows a striking asymmetry:

| FLD bias at entry | n | Mean R | Median R | Win rate | T3 hits | Stops |
|---|---|---|---|---|---|---|
| Bullish (all 3 FLDs below price) | 68 | +0.74 | +0.44 | 65% | 12 | 14 |
| Neutral | 40 | +0.97 | +0.82 | 62% | 9 | 14 |
| **Bearish (all 3 FLDs above price)** | **16** | **+4.03** | **+4.71** | **81%** | **11** | **3** |

**M-P1 LONG entries during BEARISH FLD massively outperform.** Mean R = +4.03 (5.4× the bullish-FLD edge). Win rate 81%. **T3 hit rate 11 of 16 = 69%** (vs 24% unconditional).

**Interpretation:** when all three Hurst FLDs sit above price (bearish FLD bias), the market is mechanically oversold across multiple cycles simultaneously. An M-P1 entry in this regime is catching a deeply contrarian rebound — and the rebound runs far enough to hit T3 most of the time.

This validates Dr. A's original confluence intuition. The simplified FLD I built first (40/80/120 with no canonical shift) was a null result. The CANONICAL Hurst FLD with periods 10/20/40 and shift period//2+1 produces real, dramatic confluence value.

**Practical use:**
- Trade all 124 M-P1 signals for max return (+4.23R/yr, parallel)
- OR trade only FLD-bearish entries for max edge per trade (+4.03 R/trade, +1.78R/yr)
- Hybrid: increase position size 4-5× when FLD is bearish

## 3. Sensitivity sweep

**3a. M peak threshold:**

| Threshold | Trades | Mean R | Median R |
|---|---|---|---|
| 60 | 226 | +1.09 | +0.34 |
| **65 (default)** | **124** | **+1.24** | **+0.66** |
| 70 | 46 | +1.39 | +0.83 |
| 75 | 10 | +2.26 | +1.93 |

Edge increases monotonically with threshold; trade count falls fast. Default of 65 is a reasonable balance. **Higher thresholds give better per-trade edge but fewer signals.**

**3b. Trail activation factor:**

| Factor | T3 hits | Mean R |
|---|---|---|
| 1.618x | 7 | +1.13 |
| 2.236x | 12 | +1.15 |
| 3.000x | 24 | +1.21 |
| **3.600x (Dr. A spec)** | **32** | **+1.24** |
| 3.618x | 32 | +1.24 |

Dr. A's specification of ~3.600x is optimal in the sweep. Earlier activation cuts winners short.

**3c. Max hold bars:**

| Max bars | Mean R | Median R |
|---|---|---|
| 60 | +1.14 | +0.75 |
| 120 | +1.27 | +0.62 |
| **200 (default)** | **+1.24** | **+0.66** |
| 400 | +1.32 | +0.64 |
| 800 | +1.05 | -0.65 |

Robust between 120-400 bars. 800 degrades — trades held too long deteriorate. Default of 200 is fine.

## Synthesis: the hardened system

Best per-trade-edge variant:
- Strict pattern detection (peak ≥70)
- Entry only when FLD bias (canonical 10/20/40) is bearish
- 1.618 / 2.236 / 3.618 Fib targets
- 3-bar trail activates at 3.600x range
- Max hold 200 bars

Best total-return variant:
- Default pattern detection (peak ≥65)
- Trade ALL signals (parallel positions, max 8 concurrent)
- Same Fib + trail config

## Figure

`figures/07_equity_variants.png` — three equity curves overlaid (sequential, parallel, FLD-bearish-only).

## Code changes

- `src/rsi_pattern/fld.py` — updated `compute_fld` to use canonical Hurst shift `period // 2 + 1` (was `ceil(period/2)`)
- `DEFAULT_CYCLES = (10, 20, 40)` — matches hurst-agent
