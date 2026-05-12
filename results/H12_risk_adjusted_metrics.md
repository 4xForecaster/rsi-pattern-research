# H12 — Risk-Adjusted Metrics Across the 5 Hybrid Schemes

**Date:** 2026-05-12

Step 2 of the 5-step hardening plan. H11 produced per-trade R-multiples for
the five FLD-scaled position-sizing schemes but reported only mean R and
peak R drawdown. Without proper risk-adjusted ratios there was no
apples-to-apples way to rank them. This run feeds the same trade list into
a daily equity-curve model and computes Sharpe, Sortino, Calmar, MAR, and
%-equity max drawdown.

## Setup

- **Trade list:** M-P1 LONG entries on daily DXY (1990-01-02 → 2026-05-04),
  regenerated via `position_sizing.fib_long_at_p1`. 124 completed trades
  total (68 bullish FLD / 40 neutral / 16 bearish at entry — matches H10/H11).
- **Multipliers** applied to each trade by FLD bias at entry per scheme.
  Scheme D drops bullish-FLD trades entirely → 56 trades.
- **Equity model:** 1% of initial capital risked per 1× position;
  trade PnL = R × 1% × scheme multiplier, realized on the exit date.
  Daily calendar timeline from first entry to last exit; no within-day MTM.
- **Annualization:** sqrt(252) on daily returns.
- **MAR** = full-sample CAGR / |Max DD|.
- **Calmar** = trailing 36-month CAGR / |Max DD over the same window|.
- **Max DD** is fractional equity drawdown (not R-units), so it's much
  smaller than H11's R-unit DD — the strategy compounds capital, so a late
  R-unit dip is a small fraction of the grown equity.

## Results

| Scheme | Trades | Mean R | Total R/yr | Sharpe | Sortino | Calmar | MAR | Max DD |
|---|---|---|---|---|---|---|---|---|
| **A. Pure parallel (1/1/1)** | 124 | +1.24 | +4.37 | +0.68 | +2.76 | -0.27 | +0.85 | -3.16% |
| **B. Modest (1/1/3)** | 124 | +2.28 | +8.05 | +0.52 | +4.24 | -0.29 | +1.39 | -2.80% |
| **C. Aggressive (1/1/5)** | 124 | +3.32 | +11.72 | +0.47 | +5.34 | -0.30 | +1.60 | -2.97% |
| **D. Skip bullish + 3× (0/1/3)** | 56 | +4.15 | +6.78 | +0.47 | +5.75 | -0.27 | +1.29 | -2.78% |
| **E. Conservative (0.5/1/3)** | 124 | +2.08 | +7.33 | +0.49 | +5.11 | -0.28 | +1.42 | -2.60% |

Equity curves: see `figures/08_equity_curves_risk_adjusted.png`.

## Read

1. **Sharpe favors the baseline (A).** Adding leverage on bearish-FLD trades
   raises the numerator (mean return) but raises σ proportionally more —
   the bearish-FLD pile-up of large R-multiple winners (and the occasional
   loser at 3–5× size) widens both tails of the daily-return distribution.
   This is the canonical penalty Sharpe imposes on lumpy strategies.

2. **Sortino flips the ranking — D wins.** Once you stop charging the
   strategy for upside dispersion, the picture inverts: D's +5.75 is the
   best of the five. Scaling up the bearish-FLD edge concentrates risk on
   the side that historically *paid* (81% win rate, 11/16 T3-hit), so the
   downside-deviation denominator barely moves while the numerator triples.
   For a strategy where the asymmetric edge is real, Sortino is the more
   honest read than Sharpe.

3. **MAR ranks C > E > B > D > A.** Over the full 36-year sample,
   maximum scaling (C) wins on full-sample return-per-unit-of-drawdown
   (+1.60). D loses ground here because half its calendar years carry no
   trades — annualized return is diluted across an inactive timeline.
   This is the metric you optimize if you can sit through a 14× peak
   exposure event and have the capital to do so.

4. **Calmar is negative for every scheme.** The trailing 36 months (May
   2023 → May 2026) have been a drag — yearly R-sums for scheme A:
   2022 = +30.7, 2023 = −2.5, 2024 = −1.6, 2025 = −3.0, 2026 YTD = +1.1.
   The strategy crushed it in 2022 (USD melt-up) and has chopped sideways
   since. All five schemes carry this in the trailing window. The recent
   negative Calmar is **not a property of the scaling choice** — A
   (unscaled) is also negative — so it doesn't help us pick between
   schemes; it does tell us the broader edge has cooled and warrants
   monitoring out-of-sample.

5. **Max-DD ranking is tight (−2.6% to −3.2%).** Capital-fractional DDs
   are small because 36 years of +4 to +12 R/yr compounded equity to
   several multiples of initial capital before the recent dip. The pure
   parallel (A) has the worst Max-DD even though it has the smallest
   per-trade size — its equity didn't grow as fast, so a given R-unit DD
   becomes a larger fraction of equity.

## Implications for the Step 4 recommendation (D vs C)

- **Sortino + Sharpe favor D.** D has the best Sortino (+5.75) and matches
  C on Sharpe (+0.47). D earns its risk-adjusted edge through
  *selectivity*, not leverage — same 8× peak exposure as the baseline,
  no extra capital required.

- **MAR favors C.** C's +1.60 MAR beats D's +1.29 by 24%. If capital is
  unconstrained and 14× peak exposure is acceptable, C is the
  full-sample return-maximizer.

- **The Sortino/MAR disagreement is the crux.** Sortino says D's edge is
  *cleaner* per unit of bad-side risk; MAR says C's edge is *bigger* per
  unit of worst-case capital drawdown. They're measuring different things
  and both are valid.

- **Recommendation stands: D is the default unless capital is
  unconstrained.** D's Sortino lead, identical Sharpe to C, identical
  peak-exposure to A, and 50× fewer trades (56 vs 124) make it the more
  operationally defensible choice. The trade-off vs C is +0.31 MAR
  (1.60 vs 1.29) — pay-up that buys nothing on Sharpe and *loses* +0.41
  Sortino. C remains the right pick only for an account with capacity for
  14× concurrent risk and an explicit mandate to maximize CAGR.

## Caveats

1. **Trailing-3y Calmar is uniformly negative.** All schemes have lost
   ground since mid-2022. The strategy's edge is intact in expectation
   (H9 OOS validation held) but it's in a quiet period. Resist scaling up
   exposure right now based on full-sample MAR alone.

2. **Max DD is %-equity, not R-units.** A −2.97% DD over 36 years
   understates the in-flight risk for someone starting fresh today —
   equity has grown 5–10× before that DD lands. New capital sees a much
   bigger DD relative to its starting point. Worst single calendar year
   for scheme A was 2025 at −3.0 R = −3% of initial capital.

3. **Daily returns are sparse.** Most days have zero PnL; PnL clusters on
   exit dates. Sharpe/Sortino calculated on this sparse series are valid
   but less stable than they'd be for a continuously-MTM strategy. The
   ranking is robust, the absolute levels less so.

4. **Same data, no OOS retest.** H12 reuses the H9/H10/H11 sample. No new
   information about generalization beyond what H9 already established.

## Code

- New module: `src/rsi_pattern/risk_metrics.py` (reusable —
  `build_equity_curve`, `sharpe`, `sortino`, `max_drawdown`, `cagr`,
  `mar`, `calmar`, `summarize`).
- Backtest script: `scripts/h12_risk_adjusted_backtest.py` — regenerates
  the 5 schemes from the live trade list, prints the table, writes the
  figure. Reproducible: `python3 scripts/h12_risk_adjusted_backtest.py`.
