"""State-transition forecasting: Markov baseline, HMM, and feature-based classifier."""
from __future__ import annotations
import numpy as np
import pandas as pd


def markov_baseline(states: pd.Series) -> dict:
    """Fit a simple first-order Markov chain. Return transition matrix + log-likelihood."""
    s = states.dropna().astype(str)
    unique = sorted(s.unique())
    idx = {st: i for i, st in enumerate(unique)}
    n = len(unique)
    counts = np.zeros((n, n))
    for a, b in zip(s.iloc[:-1], s.iloc[1:]):
        counts[idx[a], idx[b]] += 1
    probs = counts / counts.sum(axis=1, keepdims=True).clip(min=1)
    # Held-out log-likelihood placeholder (callers should split train/test)
    eps = 1e-9
    ll = 0.0
    for a, b in zip(s.iloc[:-1], s.iloc[1:]):
        ll += np.log(probs[idx[a], idx[b]] + eps)
    return {
        "states": unique,
        "transition_matrix": pd.DataFrame(probs, index=unique, columns=unique),
        "log_likelihood": float(ll),
        "n_transitions": int(counts.sum()),
    }


def hmm_fit(states: pd.Series, n_hidden: int = 3, n_iter: int = 50, seed: int = 0):
    """Fit a multinomial HMM with `n_hidden` hidden states.

    Imports hmmlearn lazily so the package isn't required for non-HMM users.
    Returns the fitted model and a posterior-decoded hidden state sequence.
    """
    from hmmlearn import hmm  # lazy import

    s = states.dropna().astype(str)
    unique = sorted(s.unique())
    idx = {st: i for i, st in enumerate(unique)}
    X = np.array([idx[v] for v in s]).reshape(-1, 1)

    model = hmm.CategoricalHMM(
        n_components=n_hidden,
        n_iter=n_iter,
        random_state=seed,
    )
    model.fit(X)
    hidden = model.predict(X)
    return {
        "model": model,
        "observed_states": unique,
        "hidden_sequence": pd.Series(hidden, index=s.index, name="hidden_state"),
        "log_likelihood": float(model.score(X)),
    }


def build_features(df_with_rsi_state: pd.DataFrame, rsi_col: str = "rsi14") -> pd.DataFrame:
    """Engineered features for the feature-based classifier.

    Computes for each bar:
      - rsi level, rsi slope (1-bar, 5-bar)
      - distance from key thresholds (30, 50, 70)
      - bars-in-current-state
      - previous-state encoding
    """
    out = df_with_rsi_state.copy()
    out["rsi_slope_1"] = out[rsi_col].diff()
    out["rsi_slope_5"] = out[rsi_col].diff(5)
    out["dist_50"] = out[rsi_col] - 50
    out["dist_70"] = out[rsi_col] - 70
    out["dist_30"] = out[rsi_col] - 30

    # Bars in current state
    changes = (out["state"] != out["state"].shift()).cumsum()
    out["bars_in_state"] = out.groupby(changes).cumcount() + 1

    # Previous state label (categorical encoding deferred to model layer)
    out["prev_state"] = out["state"].shift(1)

    return out


def feature_classifier_split(
    df_with_features: pd.DataFrame,
    target_horizon_bars: int = 5,
    test_fraction: float = 0.25,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Build (X_train, y_train, X_test, y_test) for next-state classification.

    y = state at t+K (K = target_horizon_bars).
    """
    feature_cols = [
        "rsi14", "rsi_slope_1", "rsi_slope_5",
        "dist_50", "dist_70", "dist_30",
        "bars_in_state",
    ]
    # One-hot encode prev_state and state
    df = df_with_features.copy()
    df["target"] = df["state"].shift(-target_horizon_bars)
    df = df.dropna(subset=feature_cols + ["target", "state", "prev_state"])

    X = pd.get_dummies(df[feature_cols + ["state", "prev_state"]])
    y = df["target"]

    split = int(len(X) * (1 - test_fraction))
    return X.iloc[:split], y.iloc[:split], X.iloc[split:], y.iloc[split:]


def train_gbm(X_train: pd.DataFrame, y_train: pd.Series, **kwargs):
    """Train a gradient-boosted classifier on the engineered features.

    Returns a fitted sklearn estimator.
    """
    from sklearn.ensemble import GradientBoostingClassifier  # lazy import
    model = GradientBoostingClassifier(**kwargs)
    model.fit(X_train, y_train)
    return model
