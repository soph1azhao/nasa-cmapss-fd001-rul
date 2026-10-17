"""Predictors from observed prefixes only; no engine identity or lifetime inputs."""
import pandas as pd
from src.load_data import SENSORS, SETTINGS

WINDOW = 10


def causal_features(frame):
    out = frame[["cycle"] + SETTINGS + SENSORS].astype(float).copy()
    grouped = frame.groupby("engine_id", sort=False)
    for sensor in SENSORS:
        out[sensor + "_mean10"] = grouped[sensor].transform(lambda s: s.rolling(WINDOW, min_periods=1).mean())
        out[sensor + "_std10"] = grouped[sensor].transform(lambda s: s.rolling(WINDOW, min_periods=1).std(ddof=0))
    return out
