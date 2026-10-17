import io
import zipfile
import numpy as np
import pandas as pd
import pytest
from src.load_data import validate_trajectories, load_trajectories, training_rul, load_test_labels, last_observations
from src.features import causal_features
from scripts.download_data import extract_fd001, REQUIRED


def test_schema_and_rul(trajectories):
    validate_trajectories(trajectories)
    target = training_rul(trajectories)
    first_engine = trajectories.engine_id == 1
    assert target[first_engine].tolist() == list(range(24, -1, -1))
    assert (target.groupby(trajectories.engine_id).last() == 0).all()


@pytest.mark.parametrize('defect', ['schema', 'missing', 'duplicate', 'order', 'cycle_gap', 'id', 'dtype'])
def test_reject_bad_data(trajectories, defect):
    frame = trajectories.copy()
    if defect == 'schema': frame = frame.drop(columns='sensor_21')
    if defect == 'missing': frame.loc[0, 'sensor_1'] = np.nan
    if defect == 'duplicate': frame = pd.concat([frame, frame.iloc[[0]]])
    if defect == 'order': frame = frame.iloc[::-1]
    if defect == 'cycle_gap': frame.loc[0, 'cycle'] = 50
    if defect == 'id': frame.loc[0, 'engine_id'] = 0
    if defect == 'dtype': frame['sensor_1'] = 'text'
    with pytest.raises(ValueError): validate_trajectories(frame)


def test_wrong_file_width(tmp_path):
    path = tmp_path / 'bad.txt'; path.write_text('1 2 3\n')
    with pytest.raises(ValueError): load_trajectories(path)


def test_features_are_causal_and_engine_local(trajectories):
    whole = causal_features(trajectories)
    prefix = trajectories[(trajectories.engine_id == 2) & (trajectories.cycle <= 12)]
    pd.testing.assert_frame_equal(whole.loc[prefix.index], causal_features(prefix))
    changed = trajectories.copy()
    changed.loc[(changed.engine_id == 2) & (changed.cycle > 12), 'sensor_1'] = 1e8
    changed.loc[changed.engine_id != 2, 'sensor_1'] = -1e8
    pd.testing.assert_frame_equal(whole.loc[prefix.index], causal_features(changed).loc[prefix.index])
    assert whole.loc[prefix.index[0], 'sensor_1_std10'] == 0
    assert whole.loc[prefix.index[-1], 'sensor_1_mean10'] == pytest.approx(prefix.sensor_1.iloc[-10:].mean())
    assert 'engine_id' not in whole and 'rul' not in whole
    assert not any('life' in c for c in whole.columns)


def test_test_label_alignment(tmp_path, trajectories):
    path = tmp_path / 'labels.txt'; path.write_text('9\n5\n')
    labels = load_test_labels(path, [1, 2])
    assert labels.to_dict() == {1: 9., 2: 5.}
    with pytest.raises(ValueError): load_test_labels(path, [2, 1])
    with pytest.raises(ValueError): load_test_labels(path, [1, 2, 3])
    last = last_observations(trajectories)
    assert last.engine_id.tolist() == list(range(1, 9))
    assert last.cycle.tolist() == list(range(25, 33))


def test_download_extracts_only_required_nested_members(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, 'w') as z:
        for name in REQUIRED: z.writestr('CMAPSS/' + name, 'example')
        z.writestr('../../unwanted.txt', 'never extract')
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, 'w') as z: z.writestr('nested.zip', inner.getvalue())
    hashes = extract_fd001(outer.getvalue(), tmp_path)
    assert set(hashes) == set(REQUIRED)
    assert {p.name for p in tmp_path.iterdir()} == set(REQUIRED)
