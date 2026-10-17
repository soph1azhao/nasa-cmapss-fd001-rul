"""Strict whitespace schema, trajectory validation, and explicit RUL alignment."""
from pathlib import Path
import numpy as np
import pandas as pd

SENSORS = [f"sensor_{i}" for i in range(1, 22)]
SETTINGS = [f"setting_{i}" for i in range(1, 4)]
COLUMNS = ["engine_id", "cycle"] + SETTINGS + SENSORS


def validate_trajectories(frame):
    if list(frame.columns) != COLUMNS:
        raise ValueError("Expected 26 columns in the documented order")
    if not all(pd.api.types.is_numeric_dtype(t) for t in frame.dtypes):
        raise ValueError("Every column must be numeric")
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("Nonfinite or missing observations")
    for name in ["engine_id", "cycle"]:
        values = frame[name]
        if (values <= 0).any() or (values != values.astype(int)).any():
            raise ValueError("IDs and cycles must be positive integers")
    if frame.duplicated(["engine_id", "cycle"]).any():
        raise ValueError("Duplicate engine-cycle observations")
    if frame.empty:
        raise ValueError("No trajectories")
    for _, group in frame.groupby("engine_id", sort=True):
        if not np.array_equal(group.cycle.to_numpy(), np.arange(1, len(group) + 1)):
            raise ValueError("Cycles must be ordered, contiguous, and start at 1")
    return frame


def load_trajectories(path):
    frame = pd.read_csv(Path(path), sep=r"\s+", header=None)
    if frame.shape[1] != len(COLUMNS):
        raise ValueError("Expected 26 whitespace-delimited columns")
    frame.columns = COLUMNS
    validate_trajectories(frame)
    frame[["engine_id", "cycle"]] = frame[["engine_id", "cycle"]].astype(int)
    return frame


def training_rul(frame):
    # Full lifetime is used exclusively as a supervised LABEL, never a feature.
    return (frame.groupby("engine_id").cycle.transform("max") - frame.cycle).rename("rul")


def last_observations(frame):
    return frame.sort_values(["engine_id", "cycle"]).groupby("engine_id").tail(1).sort_values("engine_id")


def load_test_labels(path, engine_ids):
    ids = np.asarray(engine_ids)
    values = pd.read_csv(path, sep=r"\s+", header=None)
    if values.shape != (len(ids), 1):
        raise ValueError("Expected one RUL label per engine")
    # NASA line i is the label for engine i, not for arbitrary row order.
    if not np.array_equal(ids, np.arange(1, len(ids) + 1)):
        raise ValueError("Test engine IDs must be exactly 1..N in ascending order")
    labels = values.iloc[:, 0].to_numpy(dtype=float)
    if not np.isfinite(labels).all() or (labels < 0).any():
        raise ValueError("Invalid test RUL values")
    return pd.Series(labels, index=ids, name="rul")
