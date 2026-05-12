# RSI Pattern Research

Pattern recognition on Welles Wilder's RSI(14). Detects, validates, and forecasts the **M / C / V** shape sequence observed in oscillator behavior.

## Hypothesis

RSI(14) on DXY traces a repeating sequence:
- **M** — double-peak structure near the 70-line
- **C** — consolidation / traversal between the extreme zones
- **V** — double-trough structure near the 30-line

Sequence appears to cycle M → C → V → C → M → … with some variability in duration and amplitude per cycle.

**Fractal hypothesis:** The same M/C/V topology appears on multiple timeframes (daily, 4h, 1h, 5m) of DXY, with consistent statistical properties scaled by timeframe. If true, this is evidence of intrinsic self-similarity in the oscillator.

**Predictive hypothesis:** Knowing the current state (M / C / V completion progress) provides probabilistic information about the next state transition timing and direction.

## Status

Strategy hardened across 14 hypothesis cycles (H1–H14). Production layout
as of 2026-05-12:

| Layer | TF | Spec | Role |
|---|---|---|---|
| **Execution (primary)** | **5m DXY** | [`results/H14_intraday_TRADING_SPEC.md`](results/H14_intraday_TRADING_SPEC.md) — strict-M, Scheme C, FLD (40/80/160) | Where trades are taken |
| Execution (secondary) | 15m DXY | same spec, 15m params — caveated, 18 trades in calibration window | Slow-tape / confluence |
| **Regime / bias filter** | Daily DXY | [`results/RSI_M_P1_TRADING_SPEC.md`](results/RSI_M_P1_TRADING_SPEC.md) v1.1 — loose-M, Scheme D | Situational overlay; NOT for entry timing |
| 4h / 1h | DXY | Untested for production | Reference only |

Step 4 of the hardening plan will wire the daily regime filter into the 5m
execution layer (skip 5m entries when daily FLD is fully bullish).

See [`results/H14_intraday_execution.md`](results/H14_intraday_execution.md)
for the full intraday calibration findings and
[`SYNOPSIS_2026-05-12.md`](SYNOPSIS_2026-05-12.md) for the cumulative
research narrative.

## Scope (v1)

- **Instrument:** DXY only.
- **Timeframes:** daily, 4h, 1h, 5m (for fractal self-similarity test).
- **Data source:** BarChart Premier CSV downloads. See `data/dxy/` for expected location.
- **Indicator:** RSI(14) — Wilder's smoothing (not SMA-based).
- **Predictive target:** P(next state transition | current state + features).

Independent of the Hurst FLD project. May feed confluence signals later but isn't coupled.

## Quick start

```bash
# Install
pip install -e .

# Drop your BarChart DXY CSVs into data/dxy/
#   data/dxy/dxy_daily.csv
#   data/dxy/dxy_4h.csv
#   data/dxy/dxy_1h.csv
#   data/dxy/dxy_5m.csv

# Run the exploration notebook
jupyter notebook notebooks/01_dxy_exploration.ipynb

# Or call modules directly
python -c "from rsi_pattern import data, indicators, patterns; df = data.load_dxy('1h'); df = indicators.add_rsi(df); print(patterns.detect_all(df).tail())"
```

## Repository layout

```
rsi-pattern-research/
├── docs/
│   ├── SPEC.md                       # project scope + hypotheses
│   ├── PATTERN_DEFINITIONS.md        # formal M / C / V rules
│   └── METHODOLOGY.md                # detection → validation → forecasting
├── src/rsi_pattern/
│   ├── data.py                       # BarChart CSV loader
│   ├── indicators.py                 # RSI(14), helpers
│   ├── patterns.py                   # M / C / V detection (loose)
│   ├── patterns_strict.py            # strict-M (origin<30, peaks≥75.01, wiggle≥70)
│   ├── position_sizing.py            # SURF Fib trade engine
│   ├── fld.py                        # Hurst FLD bias (daily + intraday cycles)
│   ├── intraday.py                   # H14 intraday execution engine
│   ├── risk_metrics.py               # Sharpe/Sortino/MAR + overlap-aware MTM
│   ├── validate.py                   # statistical validation + fractal tests
│   └── forecast.py                   # state-transition models
├── notebooks/01_dxy_exploration.ipynb
├── data/dxy/                         # CSVs (gitignored)
└── tests/test_patterns.py
```

## License

Private. Internal research only.
