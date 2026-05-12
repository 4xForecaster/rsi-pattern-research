# H15 — Cross-Symbol Validation (USDCHF + USDMXN)

**Date:** 2026-05-12

Final step of the 5-step hardening plan. Tests whether the DXY-tuned
two-layer M-P1 stack — daily Scheme D ([v1.1](RSI_M_P1_TRADING_SPEC.md))
plus 5m Scheme C ([H14](H14_intraday_TRADING_SPEC.md)) — generalizes to
USDCHF and USDMXN, or whether the parameters are DXY-specific and need
per-symbol retuning.

## TL;DR

| Symbol | Daily Sortino | Daily trades | Decision |
|---|---:|---:|---|
| **DXY** (reference) | **+5.75** | 56 | **GO** (already shipped, Step 4) |
| **USDMXN** | +4.41 | 26 | **SWEEP** — Sortino is strong but trade count just below the 30-floor; small calibration sweep likely flips this to GO |
| **USDCHF** | +0.87 | 25 | **NO-GO** — strategy substantially fails to generalize; needs symbol-specific calibration |

**Net read**: the framework is **partially portable**. The risk-adjusted edge
transfers cleanly to USDMXN; it does NOT transfer to USDCHF. Both outcomes
are informative — they tell us the FLD bias + RSI M-P1 setup is sensitive
to a symbol's particular cycle structure and that we cannot bulk-deploy
without per-symbol validation.

## Phase 1 — Data inventory

| Symbol | Source | Bars | Start | End | Span (yrs) |
|---|---|---:|---|---|---:|
| DXY | BarChart CSV (existing) | 9,304 | 1990-01-02 | 2026-05-04 | 36.3 |
| USDCHF | yfinance `CHF=X` (auto-cached) | 5,883 | 2003-09-17 | 2026-05-04 | 22.6 |
| USDMXN | yfinance `MXN=X` (auto-cached) | 5,838 | 2003-12-01 | 2026-05-04 | 22.4 |

**5m data** was unavailable for USDCHF and USDMXN at run time — only DXY
has a BarChart 5m CSV on disk. Per instruction "don't fabricate or resample
to fake 5m from 1h", **Phase 3 (5m Scheme C) is skipped for both** with no
proxy data. The DXY 5m baseline is unchanged from H14. When BarChart 5m
ships for these symbols, the same `scripts/h14_intraday_backtest.py`
pointed at the appropriate CSV will produce a directly-comparable read.

## Phase 2 — Daily Scheme D backtest

Same H12 rules per symbol: loose-M detector, FLD cycles `(10, 20, 40)`,
Scheme D multipliers `(bullish=0, neutral=1, bearish=3)`, 1% risk per
1× position, daily-equity (non-overlapping) metrics.

### DXY (reference — sanity check vs. H12)

| Window | Trades | Universe | Mean R | Total R/yr | Sharpe | Sortino | Calmar | MAR | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full (1990–2026) | 56 | 124 | +4.15 | +6.78 | +0.47 | **+5.75** | -0.27 | +1.29 | -2.78% |
| OOS (last 7y, 2019–2026) | 14 | 25 | +3.62 | +8.06 | +0.56 | +5.38 | -0.28 | +1.51 | -4.47% |

Numbers reproduce H12 exactly. OOS metrics are very close to full-sample —
strategy stable on its calibration symbol.

### USDCHF

| Window | Trades | Universe | Bias mix | Mean R | Total R/yr | Sharpe | **Sortino** | Calmar | MAR | Max DD |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Full (2003–2026) | 25 | 56 | 31B/17N/8b | +1.25 | +1.60 | +0.31 | **+0.87** | +1.24 | +0.17 | -8.41% |
| OOS (last 7y) | 6 | 17 | 11B/6N/**0b** | +1.37 | +1.98 | +0.54 | +2.43 | +1.25 | +1.93 | -1.00% |
| Excl-2015 (SNB shock) | 23 | 53 | 30B/17N/6b | +1.16 | +1.36 | +0.27 | +0.74 | +1.24 | +0.13 | -9.31% |

Reading:
- **Strategy fails to generalize to USDCHF on the full sample.** Sortino
  +0.87 is well below the +3.0 ship threshold. Mean R per trade is +1.25
  vs DXY's +4.15.
- **SNB-shock year (2015) actually HELPED** the strategy — excl-2015 has
  *worse* metrics (Sortino 0.74 vs 0.87; Max DD −9.31% vs −8.41%). The
  Jan 2015 franc-shock produced one or more big winners that the strategy
  caught. Removing the outlier doesn't expose hidden fragility; the rest
  of the history is just genuinely weaker.
- **OOS looks better than full** (Sortino +2.43, DD −1.0%). But only 6
  trades — far below any reasonable inference threshold. Suggestive,
  not load-bearing.
- **Bearish-FLD bias frequency is the limiting factor.** Of 56 universe
  trades, only 8 are bearish (the bucket Scheme D scales by 3×). The
  USDCHF FLD bias distribution skews bullish — close > FLD on all 3
  cycles is more common than the inverse — so the high-multiplier bucket
  is under-fed.

### USDMXN

| Window | Trades | Universe | Bias mix | Mean R | Total R/yr | Sharpe | **Sortino** | Calmar | MAR | Max DD |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Full (2003–2026) | 26 | 59 | 33B/14N/12b | +5.11 | +6.85 | +0.41 | **+4.41** | +0.58 | +1.65 | -2.70% |
| OOS (last 7y) | 7 | 14 | 7B/2N/5b | +3.61 | +5.69 | +0.51 | +2.53 | +0.57 | +0.99 | -5.23% |

Reading:
- **Strategy generalizes to USDMXN.** Sortino +4.41, Mean R +5.11,
  Max DD −2.70% — all metrics roughly comparable to DXY's.
- **Bearish-FLD bias frequency is healthier than USDCHF** (12 of 59 vs
  8 of 56 — 20% vs 14%) and the bearish-FLD trades carry the run.
- **Trade count 26 is just under the 30-floor** I set for ship-direct.
  This is the only thing keeping it from being an outright GO. The OOS
  drops to 7 trades / 7 years = ~1/year which is the right order of
  magnitude.
- **OOS Sortino +2.53** is solid but unsupported by trade count alone.

## Phase 4 — Cross-symbol comparison

Daily Scheme D, full window:

| Metric | DXY | USDCHF | USDMXN |
|---|---:|---:|---:|
| Trades | 56 | 25 | 26 |
| Mean R (weighted) | +4.15 | +1.25 | +5.11 |
| Total R/yr | +6.78 | +1.60 | +6.85 |
| Sharpe | +0.47 | +0.31 | +0.41 |
| **Sortino** | **+5.75** | **+0.87** | **+4.41** |
| Calmar | -0.27 | +1.24 | +0.58 |
| MAR | +1.29 | +0.17 | +1.65 |
| Max DD | -2.78% | -8.41% | -2.70% |

USDMXN matches DXY on Sortino-grade and total-R/yr; it falls short only on
trade-count threshold. USDCHF underperforms on every metric except
Calmar (where it's positive purely because the last 3 years happen to be
up; full-sample Sortino is what matters).

Equity curves: `figures/10_cross_symbol_equity.png`.

## Phase 5 — Go / No-Go decisions

Thresholds (mine, proposed in the Step 5 brief, kept as-is — the data does
not justify loosening them):

| Decision | Rule |
|---|---|
| **GO** | Sortino ≥ +3.0 **AND** trades ≥ 30 over the full sample |
| **NO-GO** | Sortino < +1.0 **OR** trades < 10 |
| **SWEEP** | Anything in between — run a parameter sweep before deciding |

| Symbol | Sortino | Trades | Decision | Why |
|---|---:|---:|---|---|
| **DXY** | +5.75 | 56 | **GO** | Both thresholds clear with margin |
| **USDMXN** | +4.41 | 26 | **SWEEP** | Sortino qualifies, trade count 4 short of the 30-floor |
| **USDCHF** | +0.87 | 25 | **NO-GO** | Sortino below the +1.0 floor; framework does not transfer |

**Why I kept the thresholds as proposed**: I considered loosening the
trade-count floor to 20 to account for USDCHF/USDMXN's shorter histories
(23 yrs vs DXY's 36 yrs), but that's results-driven threshold engineering.
The 30-floor is a sample-size statement, not a duration statement —
fewer trades means wider confidence intervals on Sortino regardless of
how many years they're spread over. USDMXN at 26 trades is the boundary
case the SWEEP bucket exists for.

### What "SWEEP" means for USDMXN (concrete)

A small parameter sweep (recommended, not done in this step):
1. **Lower the loose-M dip threshold** from 50 to 45 → may pick up
   additional bearish-FLD entries.
2. **Lower the inner_threshold or peak_threshold by 5 RSI points** →
   tests sensitivity to peak strictness.
3. **Try FLD cycles other than (10, 20, 40)** — Mexican peso has known
   ~120-day risk-cycle behavior; (15, 30, 60) or (20, 40, 80) may
   produce a more responsive bias label.

Target after sweep: ≥ 30 completed trades over the 22-year window while
keeping Sortino > 3.0. If that converges, ship USDMXN to the hurst-agent
config as a second production symbol.

### Why USDCHF fails (hypothesis)

The CHF's behavior since the 2015 SNB peg removal has been
range-bound; loose-M setups require a clear "two-peak overbought RSI"
structure which is sparser in a chopping symbol. The full-sample Sortino
is dragged down by 2003–2014 which was a long downtrend in USDCHF (CHF
strengthening, USD weakening relative to CHF) — long entries on RSI
M-pattern tops in that regime were systematically punished.

If Dr. A wants USDCHF in production, the framework needs either:
- a SHORT-side variant (M-pattern with FLD bullish bias as a short
  trigger), or
- a regime filter that gates entries on multi-month USD trend.

Both are outside the Step 5 scope.

## Phase 6 — Deliverables

| File | Status |
|---|---|
| [`results/H15_cross_symbol_validation.md`](H15_cross_symbol_validation.md) | this doc |
| [`figures/10_cross_symbol_equity.png`](../figures/10_cross_symbol_equity.png) | 3-curve overlay, daily Scheme D |
| [`scripts/h15_cross_symbol_validation.py`](../scripts/h15_cross_symbol_validation.py) | reproducible runner |
| `data/yfinance_cache/CHF_X_daily.csv` & `MXN_X_daily.csv` | **local cache only** (gitignored per `data/*/*.csv` rule); first run downloads via yfinance, subsequent runs read the CSV. Deterministic for the cached date range. |
| hurst-agent `config/rsi_m_p1.yaml` `symbols:` block | adds USDCHF/USDMXN as audit entries (NO-GO / SWEEP respectively, both `enabled: false`) — Dr. A flips the switch |

## Caveats

1. **5m execution layer not tested cross-symbol.** Daily-only result.
   When BarChart 5m for USDCHF/USDMXN lands, re-run H14's
   `h14_intraday_backtest.py` against each and revisit go/no-go on the 5m
   layer. The daily NO-GO for USDCHF likely propagates (without a daily
   regime tailwind the 5m doesn't have a meaningful gate), but USDMXN
   would benefit from the 5m comparison.

2. **23-year history is shorter than DXY's 36 years.** Statistical
   power is lower. A clean GO on a 23-year sample is meaningfully weaker
   evidence than the same metric on 36 years. Read all USDCHF/USDMXN
   numbers with that in mind.

3. **yfinance daily for FX uses spot bars** — slightly different from
   the BarChart futures-based DXY series. Spread/slippage assumptions
   are the H12 default (2 bps). If USDMXN goes to production, bump
   spread to **15 bps** to match retail FX intraday — but it's already
   in the GO zone on Sortino, so the bump probably won't kill it.

4. **No look-ahead in the OOS slice** — the FLD is computed on the OOS
   window only; trades are filtered to entries within the OOS dates.
   Standard time-series OOS protocol.

5. **The SNB-shock check (excl-2015) is a robustness probe, not an
   ablation.** Excluding a known outlier year shouldn't materially
   improve the strategy if the rest of the history is genuinely
   profitable. For USDCHF it doesn't — confirming that USDCHF's
   shortcoming is structural, not driven by one event.

## Code

- New runner: [`scripts/h15_cross_symbol_validation.py`](../scripts/h15_cross_symbol_validation.py)
- Cached data: `data/yfinance_cache/{CHF_X,MXN_X}_daily.csv`
- Reproducible:
  ```bash
  python3 scripts/h15_cross_symbol_validation.py
  ```
