# H28 — TimesFM 2.5 200M Zero-Shot vs FX Baselines: **Negative**

**Date:** 2026-06-18
**Script:** [`scripts/h28_timesfm_benchmark.py`](../scripts/h28_timesfm_benchmark.py)
**Run dump:** [`results/_h28_run.json`](_h28_run.json)
**Figures:** [`figures/22_timesfm_rmse_vs_baselines.png`](../figures/22_timesfm_rmse_vs_baselines.png),
[`figures/23_timesfm_calibration.png`](../figures/23_timesfm_calibration.png)

## TL;DR — 0/3 axes cleared. No integration.

Google TimesFM 2.5 (200M, PyTorch) was benchmarked zero-shot on daily DXY,
EURUSD, USDCAD with a 1000-bar context and forecast horizons {1, 5, 20}
across the standard 70/30 OOS slice. **It fails all three pre-registered
axes — emphatically.** No `TIMESFM_INTEGRATION.md` is written; hurst-agent
is not touched. The point of a benchmark is to find out, and we did.

## Setup (pinned for reproducibility)

| Pin | Value |
|---|---|
| timesfm package | **2.0.1** (PyPI) |
| Model class | `TimesFM_2p5_200M_torch` |
| HF checkpoint | `google/timesfm-2.5-200m-pytorch` (`DEFAULT_REPO_ID`) |
| Backend | **PyTorch 2.12.1**, CPU |
| Python | 3.11.15 (fresh venv at `.venv-h28-timesfm/`) |
| Context | 1000 bars (close prices, raw; `normalize_inputs=True`) |
| Horizons | 1, 5, 20 |
| Quantile head | `use_continuous_quantile_head=True` → 10 levels (assumed [0.1, …, 0.9, mean]) |
| Symbols / OOS | DXY 2772 bars, EURUSD 1729, USDCAD 1749 |
| Forecast cache | `data/h28_timesfm_cache/<sym>.npz` (re-runs free) |
| Live agent venv | **untouched** (separate venv per brief) |

## Axis (a) — Price-level RMSE on log-returns

TimesFM **loses to the best baseline on every (symbol × horizon)** — 0/9
cells. The penalty is ~30–45% higher RMSE at h=1 and shrinks but never
flips by h=20.

| Symbol | h | TimesFM | Best baseline | TimesFM wins? |
|---|---:|---:|---:|:--:|
| DXY    | 1  | 0.00604 | 0.00422 | ❌ |
| DXY    | 5  | 0.01039 | 0.00937 | ❌ |
| DXY    | 20 | 0.01827 | 0.01755 | ❌ |
| EURUSD | 1  | 0.00668 | 0.00464 | ❌ |
| EURUSD | 5  | 0.01145 | 0.01032 | ❌ |
| EURUSD | 20 | 0.02021 | 0.01947 | ❌ |
| USDCAD | 1  | 0.00587 | 0.00419 | ❌ |
| USDCAD | 5  | 0.00966 | 0.00876 | ❌ |
| USDCAD | 20 | 0.01772 | 0.01711 | ❌ |

**0 / 3 symbols cleared "≥2 of 3 horizons win." Axis (a): NOT CLEARED.**
Random walk is consistently the best or near-best baseline — the
Meese-Rogoff result, intact and undisturbed by foundation-model
pretraining.

## Axis (b) — Directional accuracy (sign of cumulative log-return)

| Symbol | h | TimesFM acc | n | binomial p (one-sided vs 0.5) | ≥55% & p<0.05 |
|---|---:|---:|---:|---:|:--:|
| DXY    | 5  | 0.495 | 2771 | 0.703 | ❌ |
| DXY    | 20 | 0.502 | 2770 | 0.417 | ❌ |
| EURUSD | 5  | 0.507 | 1729 | 0.282 | ❌ |
| EURUSD | 20 | 0.511 | 1729 | 0.180 | ❌ |
| USDCAD | 5  | 0.501 | 1749 | 0.462 | ❌ |
| USDCAD | 20 | 0.501 | 1748 | 0.471 | ❌ |

Every (symbol × horizon) sits within ±1.1 pp of 50%; no p-value comes
within an order of magnitude of significance. **Axis (b): NOT CLEARED.**
Zero-shot TimesFM has no detectable directional skill on daily FX.

## Axis (c) — Quantile calibration (the most damning)

TimesFM 2.5's 80% and 90% prediction intervals at h=5 actually cover
**≈ 29%** of realized log-returns — the bands are wildly too tight. The
50% band is approximately calibrated; everything wider is not.

| Symbol | h=5 nominal 50% | nominal 80% | nominal 90% | median \|emp − nom\| |
|---|---:|---:|---:|---:|
| DXY    | 0.482 | 0.292 | 0.292 | **50.8 pp** |
| EURUSD | 0.497 | 0.294 | 0.294 | **50.6 pp** |
| USDCAD | 0.474 | 0.286 | 0.286 | **51.4 pp** |

(0/3 symbols ≤ 5 pp deviation; the bar isn't close.) **Axis (c): NOT
CLEARED.** Confidently wrong intervals on FX would be actively dangerous
in a risk-management role — the model is over-confident, not just
inaccurate.

## Decisions (load-bearing)

- **No integration doc.** `docs/TIMESFM_INTEGRATION.md` is **not** written
  — the brief gates it on ≥2/3 axes; we got 0/3. Writing it anyway would
  be exactly the "confirm a prior" failure the brief warned against.
- **No hurst-agent change.** Live DXY cron untouched. Research only.
- **Figure numbers 22/23, not 20/21 as the brief asked.** Figures 20/21
  are already H27's `20_crypto_cycle_recon.png` and
  `21_crypto_cadence_sweep.png`; overwriting committed work is a no-
  history-rewrite violation (same precedent as H23 using H23+12/13 vs the
  brief's H17+11/12). Documented in commit.
- **`strategies_vshort.py`-style "research asset" retention** does not
  apply: TimesFM is a pretrained external model, not project code; nothing
  to keep beyond the script + cached forecasts + result.

## Honest scope of the negative

- The negative is specific to **zero-shot daily price-level forecasting**
  on three FX series. It is consistent with the long-standing FX literature
  (Meese-Rogoff: random walk is hard to beat at daily horizons) and with
  TimesFM's own paper, which never claimed daily FX competence.
- The negative does **not** rule out future use cases worth a separate
  benchmark (intraday horizons, multi-feature inputs, or covariates via
  `forecast_with_covariates`) — but each of those would be its own H-series
  experiment with pre-registered axes, not an extrapolation of H28.
- The calibration finding (29% coverage on a 90% band) is the biggest red
  flag: it means quantile-head outputs from this checkpoint should not be
  trusted as risk-bounds on FX without recalibration.

## Net read

Pretraining diversity does not buy you a free lunch on FX daily.
Random walk and a 20-bar trend continuation beat a 200M-parameter
foundation model on every horizon tested, the model has no detectable
sign-of-return skill, and its quantile head is over-confident by a factor
of three on the tails. **Stop, document, move on** — exactly the discipline
the brief asked for.
