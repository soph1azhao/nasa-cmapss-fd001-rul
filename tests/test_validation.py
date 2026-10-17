import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from src.modeling import split_engines, validation_snapshots, select_method, fit_frozen_method, make_models
from src.features import causal_features
from src.load_data import training_rul


def test_engine_groups_and_nonzero_validation(trajectories):
    fit_ids, val_ids = split_engines(trajectories)
    assert set(fit_ids).isdisjoint(val_ids)
    assert set(fit_ids + val_ids) == set(trajectories.engine_id)
    assert split_engines(trajectories) == (fit_ids, val_ids)
    heldout = trajectories[trajectories.engine_id.isin(val_ids)]
    snapshots = validation_snapshots(heldout)
    assert len(snapshots) == 3 * len(val_ids)
    assert (snapshots.rul > 0).all()
    for row in snapshots.itertuples():
        lifetime = heldout[heldout.engine_id == row.engine_id].cycle.max()
        assert row.cycle + row.rul == lifetime
        assert row.cycle == int(np.floor(row.fraction * lifetime))


def test_selection_and_fitting_cannot_read_test_labels(trajectories, monkeypatch):
    original = Path.open
    def guarded_open(self, *args, **kwargs):
        if self.name in ('RUL_FD001.txt', 'test_FD001.txt'):
            raise AssertionError('Fitting accessed official test data')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded_open)
    import src.load_data as loader
    def forbidden(*args, **kwargs): raise AssertionError('Official labels read during fitting')
    monkeypatch.setattr(loader, 'load_test_labels', forbidden)
    # Also reject all pandas CSV reads in selection/fitting.
    monkeypatch.setattr(pd, 'read_csv', forbidden)
    frozen, table, predictions = select_method(trajectories)
    fit_frozen_method(trajectories, frozen)
    assert frozen['official_test_labels_used_in_selection'] is False
    assert len(table) == 3
    assert np.isfinite(table[['mae', 'rmse']]).all().all()
    assert (predictions.prediction >= 0).all()


def test_preprocessing_fitted_only_on_training(trajectories):
    fit_ids, val_ids = split_engines(trajectories)
    training = trajectories[trajectories.engine_id.isin(fit_ids)]
    validation = trajectories[trajectories.engine_id.isin(val_ids)].copy()
    validation.loc[:, 'sensor_1'] = 1e9
    x = causal_features(training)
    pipeline = make_models()['Ridge']
    pipeline.fit(x, training_rul(training))
    scaler = pipeline.named_steps['standardscaler']
    original = scaler.mean_.copy()
    pipeline.predict(causal_features(validation))
    np.testing.assert_array_equal(original, scaler.mean_)
    expected = pipeline.named_steps['variancethreshold'].transform(pipeline.named_steps['simpleimputer'].transform(x))
    np.testing.assert_allclose(scaler.mean_, expected.mean(axis=0))


def test_real_fd001_schema_if_downloaded():
    from src.load_data import load_trajectories, load_test_labels, last_observations
    root = Path(__file__).resolve().parents[1]
    if not (root / 'data/raw/train_FD001.txt').exists():
        pytest.skip('Run the official download for integration checks')
    train = load_trajectories(root / 'data/raw/train_FD001.txt')
    test = load_trajectories(root / 'data/raw/test_FD001.txt')
    assert train.shape == (20631, 26)
    assert test.shape == (13096, 26)
    assert sorted(train.engine_id.unique()) == list(range(1, 101))
    assert sorted(test.engine_id.unique()) == list(range(1, 101))
    labels = load_test_labels(root / 'data/raw/RUL_FD001.txt', last_observations(test).engine_id)
    assert len(labels) == 100
