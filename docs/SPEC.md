# Project Spec

## Goal

Determine whether the M / C / V shape sequence observed in DXY RSI(14) is:

1. **Real** — detectable algorithmically with low false-positive rate
2. **Repeatable** — appears across multiple DXY timeframes with consistent statistical properties (fractal self-similarity)
3. **Predictive** — current pattern state provides information about the next state's timing and direction

## Hypotheses

**H1: Detection.** A formal definition of M / C / V can identify these shapes with ≥80% agreement against visual labeling.

**H2: Fractal self-similarity.** The M/C/V state-occupancy distribution and transition probabilities, measured separately on each of daily / 4h / 1h / 5m DXY, are statistically indistinguishable when normalized by timeframe.

**H3: Predictive.** Conditional forward-return distributions of DXY given current state {M, C, V} are statistically different from baseline (unconditional) distributions.

**H4: State-transition predictability.** A Markov-style model (transition matrix + state-duration distribution) predicts next-state timing better than a uniform-random baseline.

## Non-goals

- Trade execution / live signaling
- Confluence with Hurst FLD methodology (deferred to a separate downstream project)
- Multi-instrument generalization (this is DXY-only by design — DXY's behavior influences USD-pair RSI by construction)

## Success criteria

v1 ships when:

- All four hypotheses have a p-value or effect-size answer (positive or negative — falsification is a real outcome).
- The notebook reproduces every result from raw CSVs in <60 seconds.
- Code passes `pytest` with ≥80% coverage on `patterns.py` and `validate.py`.

## Open questions

- **What is C, exactly?** Two candidate definitions in `PATTERN_DEFINITIONS.md`. Need user confirmation before locking detection rules.
- **RSI smoothing variant.** Wilder's RMA is the canonical choice. Alternatives (SMA-based, EMA-based) produce slightly different oscillations. Stick with Wilder.
- **Window for "completion."** When is an M "completed"? After two confirmed peaks plus a break below 50? After N bars from the second peak? Configurable parameter — default values in `patterns.py`.

## Data

BarChart Premier CSVs for DXY:
- `data/dxy/dxy_daily.csv` — max history (decades)
- `data/dxy/dxy_4h.csv` — last 2 years
- `data/dxy/dxy_1h.csv` — last 2 years
- `data/dxy/dxy_5m.csv` — last 6 months

Expected schema (BarChart standard):
```
Symbol,Time,Open,High,Low,Last,Volume
$DXY,2024-01-02 00:00,...
```

Loader normalizes to: `timestamp, open, high, low, close, volume`.
