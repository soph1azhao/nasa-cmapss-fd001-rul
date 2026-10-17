"""Evaluation is separate from fitting and selection."""
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error


def regression_metrics(actual, predicted):
    return {"mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "mean_error": float(np.mean(np.asarray(predicted) - np.asarray(actual)))}


def error_by_rul(actual, predicted):
    frame = pd.DataFrame({"actual": np.asarray(actual), "prediction": np.asarray(predicted)})
    frame["rul_range"] = pd.cut(frame.actual, [-1, 30, 60, 100, np.inf], labels=["0-30", "31-60", "61-100", ">100"])
    rows = []
    for name, group in frame.groupby("rul_range", observed=True):
        rows.append({"rul_range": str(name), "n": len(group), **regression_metrics(group.actual, group.prediction)})
    return pd.DataFrame(rows)
