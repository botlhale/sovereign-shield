"""API response-shape regression tests."""

import math

import pandas as pd

from api_gateway import _json_records


def test_masked_numeric_values_are_json_nulls():
    records = _json_records(pd.DataFrame({"OBS_VALUE": [100.0, float("nan")]}))

    assert records == [{"OBS_VALUE": 100.0}, {"OBS_VALUE": None}]
    assert not any(math.isnan(value) for record in records for value in record.values() if isinstance(value, float))