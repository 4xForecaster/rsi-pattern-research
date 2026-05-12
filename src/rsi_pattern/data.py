"""Load and normalize BarChart Premier CSV exports."""
from __future__ import annotations
import pathlib
import pandas as pd

DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"

TIMEFRAME_FILES = {
    "daily": "dxy_daily.csv",
    "4h": "dxy_4h.csv",
    "1h": "dxy_1h.csv",
    "5m": "dxy_5m.csv",
}


def load_dxy(timeframe: str, root: pathlib.Path | None = None) -> pd.DataFrame:
    """Load DXY BarChart CSV for the given timeframe.

    Parameters
    ----------
    timeframe : {"daily", "4h", "1h", "5m"}
    root : pathlib.Path, optional
        Override the data root (defaults to <repo>/data).

    Returns
    -------
    pd.DataFrame
        Indexed by UTC timestamp, columns [open, high, low, close, volume].
    """
    if timeframe not in TIMEFRAME_FILES:
        raise ValueError(f"unknown timeframe {timeframe!r}, expected one of {list(TIMEFRAME_FILES)}")

    root = root or DATA_DIR
    path = root / "dxy" / TIMEFRAME_FILES[timeframe]
    if not path.exists():
        raise FileNotFoundError(
            f"BarChart CSV not found at {path}. Drop your downloaded CSV here."
        )

    df = pd.read_csv(path)
    # BarChart Premier CSV columns: Time, Open, High, Low, Latest, Change, %Change, Volume[, Open Int]
    # Older exports may use "Last" instead of "Latest". Data is typically sorted newest-first.
    cols = {c.lower(): c for c in df.columns}
    if "time" in cols:
        ts_col = cols["time"]
    elif "date time" in cols:
        ts_col = cols["date time"]
    elif "date" in cols and "time" in cols:
        df["__ts"] = df[cols["date"]].astype(str) + " " + df[cols["time"]].astype(str)
        ts_col = "__ts"
    else:
        raise ValueError(f"cannot find timestamp column in {list(df.columns)}")

    # Close column: BarChart uses "Latest" on modern exports, "Last" on older ones
    close_key = cols.get("latest") or cols.get("last") or cols.get("close")
    if close_key is None:
        raise ValueError(f"cannot find close/latest column in {list(df.columns)}")

    out = pd.DataFrame({
        "open": pd.to_numeric(df[cols["open"]], errors="coerce"),
        "high": pd.to_numeric(df[cols["high"]], errors="coerce"),
        "low":  pd.to_numeric(df[cols["low"]], errors="coerce"),
        "close": pd.to_numeric(df[close_key], errors="coerce"),
        "volume": pd.to_numeric(df.get(cols.get("volume", "Volume"), 0), errors="coerce"),
    })
    out.index = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    out.index.name = "timestamp"
    out = out.dropna(subset=["open", "high", "low", "close"]).sort_index()
    return out


def expected_csv_paths() -> dict[str, pathlib.Path]:
    """Where to drop your BarChart CSVs."""
    return {tf: DATA_DIR / "dxy" / fname for tf, fname in TIMEFRAME_FILES.items()}
