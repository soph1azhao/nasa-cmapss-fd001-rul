"""All model selection accepts NASA training trajectories only."""
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_selection import VarianceThreshold
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from src.features import causal_features
from src.load_data import training_rul
from src.evaluation import regression_metrics

SEED = 42
FRACTIONS = (0.4, 0.6, 0.8)


def split_engines(frame):
    fit_ids, validation_ids = train_test_split(np.sort(frame.engine_id.unique()), test_size=0.25, random_state=SEED)
    return sorted(map(int, fit_ids)), sorted(map(int, validation_ids))


def validation_snapshots(frame):
    # Three checkpoints per engine; all precede failure. Fixed before evaluation.
    records = []
    for engine_id, group in frame.groupby("engine_id", sort=True):
        lifetime = int(group.cycle.max())
        if lifetime < 4:
            raise ValueError("Need at least four cycles for pseudo-truncation")
        for fraction in FRACTIONS:
            cycle = max(1, min(lifetime - 1, int(np.floor(fraction * lifetime))))
            records.append({"engine_id": int(engine_id), "cycle": cycle, "rul": lifetime - cycle, "fraction": fraction})
    return pd.DataFrame(records)


def make_models():
    estimators = {
        "Mean baseline": DummyRegressor(strategy="mean"),
        "Ridge": Ridge(alpha=10.0),
        "Histogram gradient boosting": HistGradientBoostingRegressor(
            max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
            min_samples_leaf=30, l2_regularization=10.0,
            early_stopping=False, random_state=SEED),
    }
    return {name: make_pipeline(SimpleImputer(strategy="median"), VarianceThreshold(1e-12), StandardScaler(), model)
            for name, model in estimators.items()}


def predict_nonnegative(model, features):
    return np.maximum(0.0, model.predict(features))


def select_method(training):
    fit_ids, validation_ids = split_engines(training)
    fit = training[training.engine_id.isin(fit_ids)].copy()
    heldout = training[training.engine_id.isin(validation_ids)].copy()
    snapshots = validation_snapshots(heldout)
    # Explicitly truncate each held-out engine separately before feature generation.
    features = []
    for row in snapshots.itertuples(index=False):
        prefix = heldout[(heldout.engine_id == row.engine_id) & (heldout.cycle <= row.cycle)]
        features.append(causal_features(prefix).iloc[-1])
    x_validation = pd.DataFrame(features).reset_index(drop=True)
    x_fit, y_fit = causal_features(fit), training_rul(fit)
    comparison, predictions = [], []
    for name, model in make_models().items():
        model.fit(x_fit, y_fit)
        pred = predict_nonnegative(model, x_validation)
        comparison.append({"model": name, **regression_metrics(snapshots.rul, pred)})
        result = snapshots.copy()
        result["model"], result["prediction"] = name, pred
        predictions.append(result)
    table = pd.DataFrame(comparison).sort_values(["rmse", "mae", "model"]).reset_index(drop=True)
    selected = str(table.iloc[0].model)
    frozen = {"seed": SEED, "fit_engine_ids": fit_ids, "validation_engine_ids": validation_ids,
              "validation_fractions": list(FRACTIONS), "selection_metric": "validation RMSE",
              "target_cap": None, "rolling_window": 10, "predictions_clipped_below": 0,
              "selected_model": selected, "refit": "all 100 NASA training engines",
              "official_test_labels_used_in_selection": False,
              "model_parameters": {name: model.steps[-1][1].get_params() for name, model in make_models().items()}}
    return frozen, table, pd.concat(predictions, ignore_index=True)


def fit_frozen_method(training, frozen):
    model = make_models()[frozen["selected_model"]]
    model.fit(causal_features(training), training_rul(training))
    return model
