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

v0 scaffolding — definitions, detection logic, and validation framework in place. No statistical claims made yet.

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
│   ├── patterns.py                   # M / C / V detection
│   ├── validate.py                   # statistical validation + fractal tests
│   └── forecast.py                   # state-transition models
├── notebooks/01_dxy_exploration.ipynb
├── data/dxy/                         # CSVs (gitignored)
└── tests/test_patterns.py
```

## License

Private. Internal research only.
