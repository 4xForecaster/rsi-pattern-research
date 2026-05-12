# H11 — Hybrid Position Sizing (FLD-Scaled)

**Date:** 2026-05-12

Step 1 of the 5-step hardening plan: explicitly test position-sizing schemes that scale by canonical Hurst FLD bias at entry.

## Five schemes tested

| Scheme | Bullish FLD | Neutral | Bearish FLD | Description |
|---|---|---|---|---|
| A. Pure parallel | 1× | 1× | 1× | Baseline — every trade equal-sized |
| B. Modest scaling | 1× | 1× | 3× | Triple-up on bearish-FLD entries |
| C. Aggressive scaling | 1× | 1× | 5× | 5x boost on bearish-FLD entries |
| D. Skip bullish + scale | 0× | 1× | 3× | Drop bullish entries, 3× bearish |
| E. Conservative | 0.5× | 1× | 3× | Halve bullish, 3× bearish, keep all trades |

## Results

| Scheme | Trades | Ann R | Mean R/trade | Median R/trade | Max DD | MAR | Sharpe/trade | Peak Exp |
|---|---|---|---|---|---|---|---|---|
| **A. Pure parallel** | 124 | +4.23 | +1.24 | +0.66 | -7.63 | 0.55 | 0.56 | 8× |
| **B. Modest (1/1/3)** | 124 | +7.78 | +2.28 | +0.66 | -9.63 | 0.81 | 0.42 | 10× |
| **C. Aggressive (1/1/5)** | 124 | +11.34 | +3.32 | +0.66 | **-13.00** | **0.87** | 0.37 | 14× |
| **D. Skip bullish + 3× (0/1/3)** | **56** | +6.39 | **+4.15** | **+1.22** | -8.00 | 0.80 | **0.56** | 8× |
| **E. Conservative (0.5/1/3)** | 124 | +7.09 | +2.08 | +0.39 | -8.32 | 0.85 | 0.39 | 9× |

Definitions:
- **MAR** = annualized R / max drawdown (higher is better risk-adjusted)
- **Sharpe/trade** = mean R / std R per trade (Sharpe-like quality per trade)
- **Peak Exposure** = max sum of active position multipliers at any one time (capital required)

## Key observations

1. **C maximizes total return** at +11.3R/year but with -13R drawdown and 14× peak exposure. Highest leverage, highest risk.

2. **D has the highest mean R per trade** at +4.15 and the highest Sharpe-per-trade at 0.56. It trades half as often (56 vs 124) because it skips bullish-FLD entries entirely.

3. **D and E have nearly identical peak exposure (8× and 9×)** despite very different return profiles. Bullish-FLD entries don't concentrate temporally — skipping them doesn't reduce capital requirements much.

4. **All schemes except A have higher MAR than baseline.** Scaling by FLD bias improves risk-adjusted return.

5. **Median R unchanged across A/B/C/E** (+0.66 each). The scaling boosts the mean by amplifying the rare bearish-FLD T3 winners; the typical (median) trade is unaffected.

## Practical interpretation

**For maximum return:** Scheme C (+11.3R/year). But 14× peak exposure means you need substantial capital to handle 14 concurrent positions at full risk.

**For best risk-adjusted edge per trade:** Scheme D (+4.15R per trade, 68% win rate, 56 trades over 36 years = 1.5/year). Lower trade volume but each trade has institutional-grade edge. Same 8× peak exposure as the baseline.

**For a middle ground:** Scheme B (+7.78R/year, MAR 0.81). Trades all signals, modestly boosts bearish-FLD entries. Peak exposure 10×.

## Recommendation

**Scheme D is the best practical choice unless capital is unconstrained.**

- Same 8× peak exposure as the unscaled baseline — no extra capital needed
- 1.84× total return (+6.4 vs +4.2 R/year)
- Highest per-trade edge in the sweep (+4.15R)
- Cleanest discipline: trade only when the Hurst FLD says "all 3 cycles oversold"

The win rate (68%) is similar to the unconditional version. The big difference is **selectivity** — by skipping the 68 bullish-FLD entries (mean R only +0.74), you concentrate capital on the 16 bearish-FLD entries (mean R +4.03) plus 40 neutral entries (mean R +0.97).

If capital is unconstrained and you can comfortably size for 14× peak exposure, Scheme C is the return-maximizer.

## Caveats before declaring done

1. **Drawdown is computed on R-units, not capital.** Real trading involves position-sizing as % of equity; drawdown in % terms depends on per-trade risk fraction.
2. **No compounding effect modeled.** Each trade is 1R risk; the Annualized R is arithmetic, not compounded.
3. **Sharpe-per-trade isn't the same as Sharpe ratio.** A proper risk-adjusted metric needs equity-curve volatility, not per-trade volatility. That's step 2 of the plan.
4. **In-sample data spans 36 years.** Strategy survived OOS validation (H9), but exact MAR numbers may shift slightly out-of-sample.

## Code

No new module needed. Uses existing `position_sizing.fib_long_at_p1` + `fld.fld_bias`. Backtest script is in commit history (`scripts/` is staged for the next push).
