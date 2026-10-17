import numpy as np
import pandas as pd
import pytest
from src.load_data import COLUMNS

@pytest.fixture
def trajectories():
    rows = []
    for engine in range(1, 9):
        for cycle in range(1, 25 + engine):
            rows.append([engine, cycle, .001 * engine, .002, 100.] +
                        [float(cycle + engine + sensor) for sensor in range(21)])
    return pd.DataFrame(rows, columns=COLUMNS)
