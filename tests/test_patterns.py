"""Smoke tests for indicator computation and pattern detection."""
import numpy as np
import pandas as pd
import pytest

from rsi_pattern import indicators, patterns


@pytest.fixture
def synthetic_rsi_with_m():
    """Construct an RSI-like series with an obvious M near the top."""
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    base = 50 + 5 * np.sin(np.linspace(0, 6 * np.pi, n))
    # Inject a clear M: two peaks near 72 with a dip to 55 between
    base[60:65] = [68, 70, 72, 70, 68]
    base[65:70] = [62, 58, 55, 58, 62]
    base[70:75] = [68, 70, 72, 70, 68]
    base[75:90] = np.linspace(65, 40, 15)  # break below 50
    return pd.Series(base, index=idx, name="rsi14")


@pytest.fixture
def synthetic_rsi_with_v():
    """Construct an RSI-like series with an obvious V near the bottom."""
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    base = 50 - 5 * np.sin(np.linspace(0, 6 * np.pi, n))
    base[60:65] = [32, 30, 28, 30, 32]
    base[65:70] = [38, 42, 45, 42, 38]
    base[70:75] = [32, 30, 28, 30, 32]
    base[75:90] = np.linspace(35, 60, 15)
    return pd.Series(base, index=idx, name="rsi14")


def test_rsi_basic_properties():
    close = pd.Series(np.cumsum(np.random.default_rng(0).standard_normal(200)) + 100)
    r = indicators.rsi(close, period=14)
    valid = r.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_detect_m_finds_constructed_pattern(synthetic_rsi_with_m):
    found = patterns.detect_m(synthetic_rsi_with_m)
    assert len(found) >= 1
    m = found[0]
    assert m.kind == "M"
    assert m.completed_idx is not None


def test_detect_v_finds_constructed_pattern(synthetic_rsi_with_v):
    found = patterns.detect_v(synthetic_rsi_with_v)
    assert len(found) >= 1
    v = found[0]
    assert v.kind == "V"
    assert v.completed_idx is not None


def test_label_states_assigns_only_m_v_c(synthetic_rsi_with_m):
    df = pd.DataFrame({"rsi14": synthetic_rsi_with_m})
    out = patterns.detect_all(df)
    assert set(out["state"].unique()).issubset({"M", "V", "C"})
    # The M-formation region should be labeled "M"
    assert (out["state"].iloc[60:80] == "M").any()


def test_summarize_returns_expected_keys(synthetic_rsi_with_m):
    df = pd.DataFrame({"rsi14": synthetic_rsi_with_m})
    out = patterns.detect_all(df)
    s = patterns.summarize(out["state"])
    assert set(s.keys()) == {"occupancy_pct", "mean_run_length_bars", "transitions"}
