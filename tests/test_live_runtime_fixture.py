from decimal import Decimal

import pytest

from live_runtime_checks import synthetic_batch
from submission_history import SubmissionContext, prepare_submission, stable_hash
from datetime import datetime, timezone


def test_runtime_fixture_obeys_the_submission_contract():
    now = datetime.now(timezone.utc)
    context = SubmissionContext("live-test", stable_hash(["live-test"]), now, now)
    prepared = prepare_submission(synthetic_batch(values=("3.333",)), context)
    assert prepared.iloc[0]["OBS_VALUE"] == Decimal("3.333")
    assert prepared["IS_CURRENT"].all()
    rejected = prepare_submission(synthetic_batch(rejected=True), context)
    assert not rejected["IS_CURRENT"].any()