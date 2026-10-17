"""Run training-only selection, persist the method, then score official test once."""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from src.load_data import load_trajectories, load_test_labels, last_observations, SENSORS, training_rul
from src.features import causal_features
from src.modeling import select_method, fit_frozen_method, predict_nonnegative
from src.evaluation import regression_metrics, error_by_rul


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def save_figure(name):
    plt.tight_layout()
    plt.savefig(ROOT / "figures" / name, dpi=160, bbox_inches="tight")
    plt.close()


def eda(train, test):
    plt.style.use("seaborn-v0_8-whitegrid")
    lifetimes = train.groupby("engine_id").cycle.max()
    plt.figure(figsize=(8, 4))
    plt.hist(lifetimes, bins=18, color="#187e93", edgecolor="white")
    plt.xlabel("Run-to-failure lifetime (cycles)"); plt.ylabel("Training engines")
    plt.title("FD001: simulated engine lifetimes")
    save_figure("engine_lifetimes.png")
    fig, axes = plt.subplots(2, 2, figsize=(10, 6))
    for axis, sensor in zip(axes.flat, ["sensor_2", "sensor_7", "sensor_11", "sensor_12"]):
        for engine_id in [1, 20, 40, 60, 80]:
            group = train[train.engine_id == engine_id]
            axis.plot(group.cycle, group[sensor], alpha=.65, lw=1, label=str(engine_id))
        axis.set(title=sensor, xlabel="Observed cycle", ylabel="Measurement (NASA units)")
    axes.flat[0].legend(title="Engine", ncol=3, fontsize=7)
    fig.suptitle("Sensor trajectories vary across simulated engines")
    save_figure("sensor_trends.png")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for axis, sensor in zip(axes, ["sensor_7", "sensor_11"]):
        for engine_id in [1, 20, 40, 60, 80]:
            group = train[train.engine_id == engine_id]
            axis.plot(training_rul(group), group[sensor].rolling(10, min_periods=1).mean(), alpha=.75, label=str(engine_id))
        axis.invert_xaxis()
        axis.set(title=sensor + ": 10-cycle trailing mean", xlabel="True RUL (cycles; retrospective EDA only)", ylabel="Measurement")
    fig.suptitle("Retrospective degradation patterns; associations do not establish causation")
    save_figure("degradation_patterns.png")
    variable = [c for c in SENSORS if train[c].std() > .01]
    corr = train[variable].corr()
    plt.figure(figsize=(8, 6))
    plt.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    plt.xticks(range(len(variable)), variable, rotation=90, fontsize=8)
    plt.yticks(range(len(variable)), variable, fontsize=8)
    plt.colorbar(label="Pearson correlation"); plt.title("Pooled sensor correlations (dependent cycle observations)")
    save_figure("sensor_correlations.png")
    diagnostics = {}
    for name, frame in [("train", train), ("test", test)]:
        lengths = frame.groupby("engine_id").cycle.max()
        diagnostics[name] = {"rows": len(frame), "engines": int(frame.engine_id.nunique()),
            "columns": frame.shape[1], "engine_ids": sorted(map(int, frame.engine_id.unique())),
            "missing_values": int(frame.isna().sum().sum()), "duplicate_rows": int(frame.duplicated().sum()),
            "duplicate_engine_cycles": int(frame.duplicated(["engine_id", "cycle"]).sum()),
            "cycle_order_contiguous": True, "dtypes": {k: str(v) for k, v in frame.dtypes.items()},
            "trajectory_length_summary": lengths.describe().to_dict(),
            "constant_sensors": [c for c in SENSORS if frame[c].nunique() == 1],
            "low_variance_sensors_std_le_0_01": [c for c in SENSORS if frame[c].std() <= .01]}
    # Absolute spread depends on units; this report is descriptive, not a selector.
    train[SENSORS].agg(["mean", "std", "min", "max", "nunique"]).T.to_csv(ROOT / "results/sensor_summary.csv", index_label="sensor")
    pd.DataFrame({"engine_id": lifetimes.index, "lifetime": lifetimes.values}).to_csv(ROOT / "results/engine_lifetimes.csv", index=False)
    save_json(ROOT / "results/data_quality.json", diagnostics)
    return diagnostics


def main():
    for folder in ["results", "figures"]:
        (ROOT / folder).mkdir(exist_ok=True)
    train = load_trajectories(ROOT / "data/raw/train_FD001.txt")
    frozen, comparison, validation = select_method(train)
    # This artifact is written BEFORE official test features or labels are read.
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for folder in ["src", "scripts"] for p in sorted((ROOT / folder).glob("*.py"))}
    frozen["source_sha256"] = source_hashes
    frozen["training_file_sha256"] = hashlib.sha256((ROOT / "data/raw/train_FD001.txt").read_bytes()).hexdigest()
    save_json(ROOT / "results/frozen_method.json", frozen)
    comparison.to_csv(ROOT / "results/model_comparison.csv", index=False)
    validation.to_csv(ROOT / "results/validation_predictions.csv", index=False)
    model = fit_frozen_method(train, frozen)
    test = load_trajectories(ROOT / "data/raw/test_FD001.txt")
    last = last_observations(test)
    test_features = causal_features(test).loc[last.index]
    predictions = predict_nonnegative(model, test_features)
    labels = load_test_labels(ROOT / "data/raw/RUL_FD001.txt", last.engine_id.to_numpy())
    results = pd.DataFrame({"engine_id": last.engine_id.to_numpy(), "observed_cycle": last.cycle.to_numpy(),
                            "actual_rul": labels.to_numpy(), "predicted_rul": predictions})
    results["error"] = results.predicted_rul - results.actual_rul
    results.to_csv(ROOT / "results/test_predictions.csv", index=False)
    error_by_rul(labels, predictions).to_csv(ROOT / "results/test_error_by_rul.csv", index=False)
    quality = eda(train, test)
    metrics = {"selected_model": frozen["selected_model"], "validation": comparison.to_dict(orient="records"),
               "test": regression_metrics(labels, predictions), "test_engines": len(labels),
               "validation_engines": len(frozen["validation_engine_ids"]), "validation_snapshots": len(validation) // len(comparison),
               "test_evaluations_in_this_run": 1,
               "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                            "scikit-learn": sklearn.__version__, "matplotlib": matplotlib.__version__}}
    save_json(ROOT / "results/metrics.json", metrics)
    plt.figure(figsize=(6, 5))
    plt.scatter(labels, predictions, c="#187e93", alpha=.8, edgecolors="white")
    lim = max(max(labels), max(predictions)) * 1.05
    plt.plot([0, lim], [0, lim], "--", color="#b8512b", label="Perfect prediction")
    plt.xlabel("Actual RUL (cycles)"); plt.ylabel("Predicted RUL (cycles)")
    plt.title("Official FD001 test: " + frozen["selected_model"]); plt.legend()
    save_figure("prediction_vs_actual.png")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].hist(results.error, bins=18, color="#187e93", edgecolor="white")
    axes[0].set(xlabel="Predicted minus actual RUL (cycles)", ylabel="Test engines", title="Prediction error distribution")
    axes[1].scatter(labels, results.error, color="#187e93", alpha=.8)
    axes[1].axhline(0, ls="--", color="#b8512b")
    axes[1].set(xlabel="Actual RUL (cycles)", ylabel="Prediction error (cycles)", title="Positive error overestimates remaining life")
    save_figure("prediction_errors.png")
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    main()
