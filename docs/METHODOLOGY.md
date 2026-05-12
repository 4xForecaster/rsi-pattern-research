# Methodology

Four phases: ingest → detect → validate → forecast.

## Phase 1: Ingest

`src/rsi_pattern/data.py` loads BarChart CSVs and normalizes to a standard OHLCV frame indexed by UTC timestamp.

- Auto-detect BarChart's column names (`Symbol, Time, Open, High, Low, Last, Volume`)
- Parse timezone-aware timestamps (BarChart typically exports in exchange-local time)
- Drop rows with missing OHLC
- Sort ascending by timestamp
- Return `pd.DataFrame` with columns `[open, high, low, close, volume]`

## Phase 2: Detect

Two-step detection:

**Step 2a — Compute Wilder RSI(14).** `src/rsi_pattern/indicators.py`:

```
gain = max(close.diff(), 0)
loss = max(-close.diff(), 0)
avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()    # Wilder smoothing
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
rs = avg_gain / avg_loss
rsi = 100 - 100 / (1 + rs)
```

**Step 2b — Pattern detection.** `src/rsi_pattern/patterns.py`:

1. Find all local maxima and minima of RSI via `scipy.signal.find_peaks` with prominence + distance filters.
2. For each pair of adjacent peaks (or troughs) within `max_span_bars`, test against M / V definitions.
3. Track "open" patterns waiting for completion (RSI to cross 50). Mark as completed when it does.
4. Assign every bar to a state label: `M`, `M_progressing`, `V`, `V_progressing`, `C`.

Output: a `state` column appended to the OHLCV+RSI frame.

## Phase 3: Validate

`src/rsi_pattern/validate.py`. Tests for each hypothesis:

**H1 — Detection quality.** Once you label ~30-50 patterns visually on a chart segment, compute precision/recall vs. the detector. Target: precision ≥ 0.8, recall ≥ 0.7.

**H2 — Fractal self-similarity.** For each timeframe of DXY:
- State occupancy distribution (% bars in M / C / V).
- Empirical transition matrix between states.
- Mean and std of state durations (in bars and in calendar time).

Test: are these distributions statistically indistinguishable across timeframes when normalized? Use:
- Kolmogorov-Smirnov on state-duration distributions (in calendar-time)
- Chi-squared on transition matrices
- Bootstrap CI on state-occupancy %

**H3 — Conditional forward returns.** For each completed pattern, compute DXY return over `K` bars forward (`K` configurable: 1, 5, 20, 60 bars). Compare:
- Conditional distribution `r | state=M_completed` vs unconditional `r`
- Mann-Whitney U or KS test
- Effect size (Cohen's d)

**H4 — State-transition predictability.** Train a simple Markov model on the state sequence; evaluate next-state log-likelihood vs. a uniform-random baseline.

## Phase 4: Forecast

`src/rsi_pattern/forecast.py`. Three modeling tracks:

### 4a. Markov chain baseline

Empirical transition matrix `P(s_{t+1} | s_t)`. Trivial to fit, no learning rate, gives baseline accuracy for next-state prediction.

### 4b. HMM (hidden Markov model)

If the observed M / C / V labels are believed to be noisy projections of a smaller set of true hidden regimes, an HMM with K hidden states (e.g., 2-5) and the M/C/V labels as observations can recover the hidden dynamics.

`hmmlearn.MultinomialHMM` with `n_components` tuned via AIC/BIC.

Test whether HMM beats the Markov baseline on held-out log-likelihood. If it doesn't, the M/C/V labels ARE the dynamics — no hidden regime structure beyond what's already observed.

### 4c. Feature-based classifier

Compute features at each bar:
- Current state + bars-in-current-state
- RSI level, RSI slope (1-bar, 5-bar)
- Distance from 50, 70, 30 lines
- Previous state, previous state duration

Train a gradient-boosted classifier (e.g., `sklearn.GradientBoostingClassifier` or LightGBM) to predict either:
- (i) Next state at horizon `K`
- (ii) Time-to-next-transition

Compare ROC-AUC, log-loss vs. Markov baseline.

## What "predictive" means here

Per user scope: predict the **state transitions** (M → C → V or similar), not directly the price. Price predictability is a downstream test (H3) and would feed a confluence signal later. The intrinsic state-transition model is the first deliverable.

## What gets reported

`notebooks/01_dxy_exploration.ipynb` is the reproducible report. Sections:

1. Data load + sanity checks (gap detection, NaN check, timestamp continuity)
2. RSI(14) computation + plot
3. Pattern detection — visualize labeled segments on RSI
4. H1 — detector quality (manual labels vs. detector output)
5. H2 — fractal self-similarity across timeframes
6. H3 — conditional forward returns
7. H4 — state-transition Markov + HMM comparison
8. Summary table: each hypothesis with p-value / effect size

Reproducible from raw CSVs in <60s.
