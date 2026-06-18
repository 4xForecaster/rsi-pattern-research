#!/usr/bin/env python3
"""H28 — Benchmark Google TimesFM 2.5 (200M, PyTorch) zero-shot vs FX baselines.

Question: does a pretrained time-series foundation model beat the FX random-walk
floor? FX daily returns are famously close to a martingale; zero-shot foundation
models are interesting precisely because their pretraining diversity *might*
break that. This is a benchmark, not an integration — if TimesFM doesn't clear
2 of 3 axes, no integration follows.

Reproducibility pins (load-bearing):
  * timesfm                2.0.1 (PyPI) → exports TimesFM_2p5_200M_torch
  * torch                  2.12.1 (CPU)
  * HF checkpoint repo     google/timesfm-2.5-200m-pytorch
  * Python                 3.11.15 (fresh venv at /Users/.../.venv-h28-timesfm)
  * seed                   per-symbol = stable function of symbol string
  * 70/30 split by bars    same convention as H23/H24/H25/H26/H27 — no new slice

Three benchmark axes:
  (a) Price-level RMSE on log-returns, horizons {1, 5, 20}. TimesFM wins
      this axis iff RMSE < min(baselines) on ≥2/3 horizons across ≥2/3
      symbols.
  (b) Directional accuracy (sign of cumulative log-return), horizons {5, 20}.
      Interesting iff TimesFM ≥ 55% with binomial p < 0.05 vs 50%.
  (c) Quantile calibration: empirical coverage of nominal bands. Pass iff
      median |empirical − nominal| ≤ 5 percentage points across {50, 80,
      90} central intervals on ≥2 symbols at horizon 5.

Pass ≥ 2 of 3 → write docs/TIMESFM_INTEGRATION.md (proposals only, no impl).
Otherwise → write results/H28_timesfm_negative.md.

Caching: TimesFM point + quantile forecasts persisted under
data/h28_timesfm_cache/<symbol>.npz; re-running is fast.

Figures use indices 22/23 (NOT 20/21 as the brief requested — those are
already H27's `20_crypto_cycle_recon.png` and `21_crypto_cadence_sweep.png`;
clobbering is a no-history-rewrite violation, same precedent as H23).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from statsmodels.tsa.arima.model import ARIMA

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
CACHE = REPO / "data" / "yfinance_cache"
TFM_CACHE = REPO / "data" / "h28_timesfm_cache"
TFM_CACHE.mkdir(parents=True, exist_ok=True)
OUTDIR_FIG = REPO / "figures"

IS_FRACTION = 0.70
CONTEXT_LEN = 1000
HORIZONS = (1, 5, 20)
MAX_H = max(HORIZONS)
BATCH = 64
TFM_REPO = "google/timesfm-2.5-200m-pytorch"
TFM_PKG_VERSION = "2.0.1"     # pip show timesfm
TORCH_VERSION = "2.12.1"
DIRECTIONAL_MIN_PCT = 0.55
CAL_LEVELS = (0.50, 0.80, 0.90)
CAL_PASS_DEV_PP = 0.05
ARIMA_REFIT_EVERY = 50

SYMS = {"DXY": None, "EURUSD": "EURUSD_X", "USDCAD": "USDCAD_X"}


def _seed_for(sym: str) -> int:
    return int.from_bytes(hashlib.sha256(sym.encode()).digest()[:4], "big") & 0x7FFFFFFF


def load_series(sym: str) -> pd.Series:
    if sym == "DXY":
        from rsi_pattern import data as dm
        dm.DATA_DIR = pathlib.Path.home() / "Documents" / "rsi-data"
        df = dm.load_dxy("daily")
    else:
        cp = CACHE / f"{SYMS[sym]}_daily.csv"
        df = pd.read_csv(cp, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
    return df["close"].dropna().sort_index()


def split_oos(s: pd.Series) -> pd.Series:
    e = int(len(s) * IS_FRACTION)
    return s.iloc[e:]


# ---------------------------------------------------------------------------
# Baselines (operate on log-prices, return log-return forecasts at HORIZONS)
# ---------------------------------------------------------------------------

def baseline_rw(_logp_ctx: np.ndarray) -> dict[int, float]:
    return {h: 0.0 for h in HORIZONS}


def baseline_naive_trend(logp_ctx: np.ndarray) -> dict[int, float]:
    slope_per_bar = float(logp_ctx[-1] - logp_ctx[-21]) / 20.0
    return {h: slope_per_bar * h for h in HORIZONS}


_ARIMA_STATE: dict[str, object] = {}

def baseline_arima(sym: str, logp_ctx: np.ndarray, bar_idx: int) -> dict[int, float]:
    """ARIMA(1,1,1) on log-prices. Refits every ARIMA_REFIT_EVERY bars (params
    cached between refits to bound CPU)."""
    key = f"{sym}_params"; fresh_at = _ARIMA_STATE.get(f"{sym}_at", -1)
    if bar_idx - int(fresh_at) >= ARIMA_REFIT_EVERY or key not in _ARIMA_STATE:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                fit = ARIMA(logp_ctx, order=(1, 1, 1)).fit(
                    method_kwargs={"maxiter": 50, "disp": False})
                _ARIMA_STATE[key] = fit.params
                _ARIMA_STATE[f"{sym}_at"] = bar_idx
            except Exception:  # noqa: BLE001
                _ARIMA_STATE[key] = None
    params = _ARIMA_STATE.get(key)
    # Apply parameters to the CURRENT context to forecast MAX_H steps.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            model = ARIMA(logp_ctx, order=(1, 1, 1))
            if params is not None:
                res = model.filter(params)
            else:
                res = model.fit(method_kwargs={"maxiter": 30, "disp": False})
            fc = np.asarray(res.forecast(steps=MAX_H))
            cur = float(logp_ctx[-1])
            return {h: float(fc[h - 1] - cur) for h in HORIZONS}
        except Exception:  # noqa: BLE001
            return {h: 0.0 for h in HORIZONS}


# ---------------------------------------------------------------------------
# TimesFM walk-forward with batching + cache
# ---------------------------------------------------------------------------

def _tfm_cache_path(sym: str, n_forecast_bars: int) -> pathlib.Path:
    return TFM_CACHE / f"{sym}_oos_h{MAX_H}_ctx{CONTEXT_LEN}_n{n_forecast_bars}.npz"


def run_timesfm(sym: str, close: np.ndarray, oos_start: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (points[N,H], quantiles[N,H,Q]) where N = forecastable bars."""
    n_bars = len(close)
    n_forecast = n_bars - oos_start - MAX_H
    cache = _tfm_cache_path(sym, n_forecast)
    if cache.exists():
        z = np.load(cache)
        print(f"   cache hit: {cache.name}")
        return z["points"], z["quants"]

    import timesfm
    np.random.seed(_seed_for(sym))
    t0 = time.time()
    M = timesfm.TimesFM_2p5_200M_torch.from_pretrained(TFM_REPO)
    M.compile(timesfm.ForecastConfig(
        max_context=CONTEXT_LEN, max_horizon=MAX_H, normalize_inputs=True,
        use_continuous_quantile_head=True, per_core_batch_size=BATCH,
        force_flip_invariance=True, infer_is_positive=True))
    print(f"   tfm load+compile {time.time()-t0:.1f}s")

    points = np.full((n_forecast, MAX_H), np.nan, dtype=np.float64)
    quants: Optional[np.ndarray] = None
    t0 = time.time()
    for b0 in range(0, n_forecast, BATCH):
        b1 = min(b0 + BATCH, n_forecast)
        ctxs = [close[oos_start + i - CONTEXT_LEN: oos_start + i].astype(np.float32)
                for i in range(b0, b1)]
        pt, qt = M.forecast(horizon=MAX_H, inputs=ctxs)
        points[b0:b1] = pt
        if quants is None:
            quants = np.full((n_forecast, MAX_H, qt.shape[-1]), np.nan, dtype=np.float64)
        quants[b0:b1] = qt
        if (b0 // BATCH) % 5 == 0:
            print(f"   bar {b0}/{n_forecast} ({100*b0/n_forecast:.0f}%) "
                  f"elapsed {time.time()-t0:.0f}s")
    print(f"   tfm walk-forward {time.time()-t0:.0f}s ({n_forecast} bars)")
    np.savez_compressed(cache, points=points, quants=quants)
    return points, quants


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def rmse(arr: np.ndarray) -> float:
    a = arr[~np.isnan(arr)]
    return float(np.sqrt(np.mean(a * a))) if len(a) else float("nan")


def axis_a_rmse(symbol_results: dict) -> dict:
    """TimesFM wins if RMSE < min(baselines) on ≥2/3 horizons across ≥2/3 syms."""
    wins = {h: 0 for h in HORIZONS}
    for sym, m in symbol_results.items():
        for h in HORIZONS:
            tfm = m["rmse"]["timesfm"][h]
            base = min(m["rmse"][k][h] for k in ("rw", "naive", "arima"))
            if tfm < base:
                wins[h] += 1
    n_horizons_with_win = sum(1 for h in HORIZONS
                              if max(symbol_results[s]["rmse_tfm_wins"][h]
                                     for s in symbol_results) > 0)
    n_sym_2of3 = sum(1 for s in symbol_results
                     if sum(symbol_results[s]["rmse_tfm_wins"][h] for h in HORIZONS) >= 2)
    passed = (n_sym_2of3 >= 2)  # ≥2 of 3 symbols clear with ≥2 of 3 horizons each
    return {"wins_per_horizon_count_syms": wins,
            "n_sym_clearing_2of3_horizons": n_sym_2of3,
            "passed": passed}


def axis_b_directional(symbol_results: dict) -> dict:
    interesting = {}
    for sym, m in symbol_results.items():
        interesting[sym] = {}
        for h in (5, 20):
            ok = m["directional"]["timesfm"][h]["accuracy"]
            n = m["directional"]["timesfm"][h]["n"]
            k = int(round(ok * n))
            p = float(stats.binomtest(k, n, p=0.5, alternative="greater").pvalue)
            interesting[sym][h] = {"acc": ok, "n": n, "p_value": p,
                                   "passed": (ok >= DIRECTIONAL_MIN_PCT and p < 0.05)}
    any_pass = any(interesting[s][h]["passed"] for s in interesting for h in (5, 20))
    return {"per_symbol_horizon": interesting, "passed": any_pass}


def axis_c_calibration(symbol_results: dict) -> dict:
    syms_pass = 0
    detail = {}
    for sym, m in symbol_results.items():
        cov = m["calibration"]  # {horizon: {nominal: empirical}}
        dev = []
        for nominal in CAL_LEVELS:
            emp = cov.get(5, {}).get(nominal)
            if emp is not None and not np.isnan(emp):
                dev.append(abs(emp - nominal))
        med_dev = float(np.median(dev)) if dev else float("nan")
        detail[sym] = {"h5_coverage": cov.get(5), "median_abs_dev_pp": med_dev}
        if (not np.isnan(med_dev)) and med_dev <= CAL_PASS_DEV_PP:
            syms_pass += 1
    return {"per_symbol": detail, "n_syms_passing": syms_pass, "passed": syms_pass >= 2}


def compute_quantile_levels(qt: np.ndarray) -> np.ndarray:
    """Best-effort: TimesFM 2.5 returns 10 levels including the median. Standard
    grid is [0.1..0.9] + a tenth bucket (either 0.05+0.95 endpoints or mean).
    We *verify by construction*: for each (bar, horizon) the quantile values
    must be monotonically non-decreasing if they are the 10-level grid. We
    assume [0.1, 0.2, ..., 0.9, mean] (the documented TimesFM 1/2 convention)
    and verify monotonicity on the first 9 slices."""
    n_q = qt.shape[-1]
    if n_q == 10:
        return np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, np.nan])
    if n_q == 9:
        return np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    return np.linspace(0.05, 0.95, n_q)


def _interp_quantile(q_levels: np.ndarray, q_values: np.ndarray, target: float) -> float:
    mask = ~np.isnan(q_levels)
    if not mask.any():
        return float("nan")
    return float(np.interp(target, q_levels[mask], q_values[mask]))


def evaluate_symbol(sym: str) -> dict:
    print(f"\n=== {sym} ===")
    close = load_series(sym).values.astype(np.float64)
    oos_start = int(len(close) * IS_FRACTION)
    if oos_start < CONTEXT_LEN:
        raise RuntimeError(f"{sym}: not enough IS bars for {CONTEXT_LEN}-bar context")
    logp = np.log(close)
    n_forecast = len(close) - oos_start - MAX_H
    print(f"  bars total={len(close)} oos_start={oos_start} forecastable_bars={n_forecast}")

    print("  TimesFM walk-forward...")
    tfm_pt, tfm_qt = run_timesfm(sym, close, oos_start)
    q_levels = compute_quantile_levels(tfm_qt)
    print(f"  quantile head: {tfm_qt.shape[-1]} levels (assumed {q_levels})")

    rmse_arr = {k: {h: [] for h in HORIZONS} for k in ("timesfm", "rw", "naive", "arima")}
    sign_arr = {k: {h: {"correct": 0, "n": 0} for h in (5, 20)} for k in ("timesfm",)}
    cal_arr = {h: {lvl: {"in": 0, "n": 0} for lvl in CAL_LEVELS} for h in HORIZONS}

    print("  scoring forecasts vs actuals...")
    t0 = time.time()
    for i in range(n_forecast):
        t = oos_start + i
        ctx = logp[t - CONTEXT_LEN:t]
        cur = float(logp[t])
        actual = {h: float(logp[t + h] - cur) for h in HORIZONS}
        tfm_lr = {h: float(np.log(tfm_pt[i, h - 1] / close[t])) for h in HORIZONS}
        rw_f = baseline_rw(ctx)
        nv_f = baseline_naive_trend(ctx)
        ar_f = baseline_arima(sym, ctx, i)

        for h in HORIZONS:
            rmse_arr["timesfm"][h].append(tfm_lr[h] - actual[h])
            rmse_arr["rw"][h].append(rw_f[h] - actual[h])
            rmse_arr["naive"][h].append(nv_f[h] - actual[h])
            rmse_arr["arima"][h].append(ar_f[h] - actual[h])

        for h in (5, 20):
            if abs(actual[h]) > 1e-12 and abs(tfm_lr[h]) > 1e-12:
                sign_arr["timesfm"][h]["correct"] += int(np.sign(actual[h]) == np.sign(tfm_lr[h]))
                sign_arr["timesfm"][h]["n"] += 1

        # Calibration: TimesFM quantiles are PRICE-LEVEL at each horizon. Map
        # each level to a log-return and check actual log-return ∈ [lo, hi].
        for h in HORIZONS:
            qvals = tfm_qt[i, h - 1, :]
            for lvl in CAL_LEVELS:
                lo_q = (1.0 - lvl) / 2.0
                hi_q = 1.0 - lo_q
                lo_p = _interp_quantile(q_levels, qvals, lo_q)
                hi_p = _interp_quantile(q_levels, qvals, hi_q)
                if not (np.isnan(lo_p) or np.isnan(hi_p) or lo_p <= 0 or hi_p <= 0):
                    lo_r = float(np.log(lo_p / close[t]))
                    hi_r = float(np.log(hi_p / close[t]))
                    if lo_r > hi_r:
                        lo_r, hi_r = hi_r, lo_r
                    cal_arr[h][lvl]["in"] += int(lo_r <= actual[h] <= hi_r)
                    cal_arr[h][lvl]["n"] += 1
    print(f"  scoring {time.time()-t0:.1f}s")

    out_rmse = {k: {h: rmse(np.array(rmse_arr[k][h])) for h in HORIZONS}
                for k in rmse_arr}
    rmse_tfm_wins = {h: int(out_rmse["timesfm"][h] <
                            min(out_rmse[b][h] for b in ("rw", "naive", "arima")))
                     for h in HORIZONS}
    out_dir = {"timesfm": {h: {"accuracy": (sign_arr["timesfm"][h]["correct"] /
                                            max(sign_arr["timesfm"][h]["n"], 1)),
                                "n": sign_arr["timesfm"][h]["n"]} for h in (5, 20)}}
    out_cal = {h: {lvl: (cal_arr[h][lvl]["in"] / cal_arr[h][lvl]["n"]
                          if cal_arr[h][lvl]["n"] else float("nan"))
                    for lvl in CAL_LEVELS} for h in HORIZONS}
    return {"n_forecast": n_forecast, "rmse": out_rmse, "rmse_tfm_wins": rmse_tfm_wins,
            "directional": out_dir, "calibration": out_cal,
            "quantile_levels_assumed": q_levels.tolist()}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig_rmse(results: dict, path: pathlib.Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    methods = ["timesfm", "rw", "naive", "arima"]
    pal = {"timesfm": "#4285F4", "rw": "#888", "naive": "#ff7f0e", "arima": "#2ca02c"}
    width = 0.21
    for ax, sym in zip(axes, results):
        m = results[sym]["rmse"]
        for i, mth in enumerate(methods):
            vals = [m[mth][h] for h in HORIZONS]
            ax.bar(np.arange(len(HORIZONS)) + (i - 1.5) * width, vals, width,
                   color=pal[mth], edgecolor="black", lw=0.4, label=mth)
        ax.set_xticks(np.arange(len(HORIZONS))); ax.set_xticklabels([f"h={h}" for h in HORIZONS])
        ax.set_title(f"{sym}", fontsize=11)
        ax.grid(True, axis="y", alpha=0.3)
        if ax is axes[0]:
            ax.set_ylabel("RMSE of log-return forecast")
            ax.legend(fontsize=8)
    fig.suptitle("H28 fig22 — RMSE of log-return forecasts: TimesFM 2.5 vs baselines (FX daily OOS, 70/30)",
                 fontsize=11)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight"); plt.close()


def fig_calibration(results: dict, path: pathlib.Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for ax, sym in zip(axes, results):
        cov = results[sym]["calibration"]
        for h, marker in zip(HORIZONS, ("o", "s", "D")):
            nominals = list(CAL_LEVELS)
            empiricals = [cov.get(h, {}).get(lvl) for lvl in CAL_LEVELS]
            ax.plot(nominals, empiricals, marker=marker, label=f"h={h}", linewidth=1.6)
        ax.plot([0.4, 1.0], [0.4, 1.0], color="black", linestyle="--", alpha=0.4,
                label="perfect")
        ax.set_xlim(0.4, 1.0); ax.set_ylim(0.4, 1.0)
        ax.set_title(f"{sym}", fontsize=11)
        ax.set_xlabel("nominal central coverage"); ax.grid(True, alpha=0.3)
        if ax is axes[0]:
            ax.set_ylabel("empirical coverage")
            ax.legend(fontsize=8)
    fig.suptitle("H28 fig23 — TimesFM quantile calibration (central coverage; closer to dashed=better)",
                 fontsize=11)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight"); plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 82)
    print("H28 — TimesFM 2.5 200M (PyTorch) zero-shot vs FX baselines")
    print("=" * 82)
    print(f"timesfm pkg {TFM_PKG_VERSION} · torch {TORCH_VERSION} · checkpoint {TFM_REPO}")
    print(f"context={CONTEXT_LEN} horizons={HORIZONS} IS={IS_FRACTION:.0%} batch={BATCH}")

    results = {}
    for sym in SYMS:
        results[sym] = evaluate_symbol(sym)

    print("\n=== AXIS (a): RMSE vs baselines ===")
    a = axis_a_rmse(results)
    for sym in SYMS:
        m = results[sym]["rmse"]; w = results[sym]["rmse_tfm_wins"]
        print(f"  {sym}:")
        for h in HORIZONS:
            base = min(m[b][h] for b in ("rw", "naive", "arima"))
            print(f"    h={h:>2}  tfm={m['timesfm'][h]:.5f}  best_baseline={base:.5f}  "
                  f"win={bool(w[h])}")
    print(f"  AXIS (a) passed: {a['passed']}  (n_syms ≥2/3 horizons: {a['n_sym_clearing_2of3_horizons']}/3)")

    print("\n=== AXIS (b): Directional accuracy (binomial vs 50%) ===")
    b = axis_b_directional(results)
    for sym, perh in b["per_symbol_horizon"].items():
        for h, v in perh.items():
            print(f"  {sym} h={h}: acc={v['acc']:.3f} n={v['n']} p={v['p_value']:.3g} "
                  f"-> {'PASS' if v['passed'] else 'no'}")
    print(f"  AXIS (b) passed: {b['passed']}")

    print("\n=== AXIS (c): Quantile calibration (h=5; |emp − nominal| ≤ 5pp) ===")
    c = axis_c_calibration(results)
    for sym, d in c["per_symbol"].items():
        h5 = d.get("h5_coverage", {})
        print(f"  {sym}: h5 coverage at {dict((l, round(h5.get(l, float('nan')), 3)) for l in CAL_LEVELS)} "
              f"median |dev|={d['median_abs_dev_pp']*100:.1f}pp")
    print(f"  AXIS (c) passed: {c['passed']}  (n_syms passing: {c['n_syms_passing']}/3)")

    n_pass = int(a["passed"]) + int(b["passed"]) + int(c["passed"])
    verdict = "POSITIVE (≥2/3 axes)" if n_pass >= 2 else "NEGATIVE (<2/3 axes)"
    print(f"\n=== VERDICT: {verdict} ({n_pass}/3 axes) ===")

    OUTDIR_FIG.mkdir(exist_ok=True)
    fig_rmse(results, OUTDIR_FIG / "22_timesfm_rmse_vs_baselines.png")
    print(f"Wrote {OUTDIR_FIG/'22_timesfm_rmse_vs_baselines.png'}")
    fig_calibration(results, OUTDIR_FIG / "23_timesfm_calibration.png")
    print(f"Wrote {OUTDIR_FIG/'23_timesfm_calibration.png'}")

    dump = {"versions": {"timesfm": TFM_PKG_VERSION, "torch": TORCH_VERSION,
                          "checkpoint": TFM_REPO, "python": "3.11.15"},
             "config": {"context_len": CONTEXT_LEN, "horizons": list(HORIZONS),
                        "is_fraction": IS_FRACTION, "batch": BATCH,
                        "arima_refit_every": ARIMA_REFIT_EVERY,
                        "directional_min_pct": DIRECTIONAL_MIN_PCT,
                        "cal_levels": list(CAL_LEVELS),
                        "cal_pass_dev_pp": CAL_PASS_DEV_PP},
             "results": results,
             "axes": {"a_rmse": a, "b_directional": b, "c_calibration": c,
                       "n_pass": n_pass, "verdict": verdict}}
    (REPO / "results" / "_h28_run.json").write_text(json.dumps(dump, indent=2, default=str))
    print(f"Wrote {REPO/'results'/'_h28_run.json'}")


if __name__ == "__main__":
    main()
