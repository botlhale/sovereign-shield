from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from deltalake import DeltaTable

from submission_history import SubmissionContext, merge_local_submission, stable_hash

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def context(identity, sequence=0):
    return SubmissionContext(identity, stable_hash([identity]), START + timedelta(days=sequence), START + timedelta(days=sequence, minutes=1))


def batch(values=("1.111", "2.222"), country="CA", period="2026-Q1", rejected=False):
    return pd.DataFrame([{
        "TIME_SERIES_CODE": f"Q.S.C.A.USD.F.5J.A.{country}.{sector}.DE",
        "DATE": period, "AGG_CODE": "LBSR", "OBS_VALUE": value,
        "OBS_CONF": "F", "OBS_STATUS": "A", "QUALITY_STATUS": "FAIL" if rejected else "PASS",
        "BATCH_STATUS": "QUARANTINE" if rejected else "PUBLISHED",
        "FAILED_RULE_ID": "LBS_CC:04" if rejected and index == 0 else None,
    } for index, (sector, value) in enumerate(zip(("B", "N"), values))])


def test_replay_is_noop_but_identical_new_filing_is_retained(tmp_path):
    path = tmp_path / "history"
    merge_local_submission(path, batch(), context("first"))
    assert merge_local_submission(path, batch(), context("first")) == 0
    assert DeltaTable(str(path)).version() == 0
    merge_local_submission(path, batch(), context("new-identical", 1))
    table = DeltaTable(str(path))
    rows = table.to_pandas()
    assert table.version() == 1
    assert len(rows) == 4
    assert rows["IS_CURRENT"].sum() == 2
    assert not rows["RECORD_ID"].duplicated().any()


def test_shorter_accepted_snapshot_retires_only_its_scope(tmp_path):
    path = tmp_path / "history"
    merge_local_submission(path, batch(), context("ca-q1"))
    merge_local_submission(path, batch(country="US"), context("us-q1"))
    merge_local_submission(path, batch(period="2026-Q2"), context("ca-q2"))
    merge_local_submission(path, batch(values=("3.333",)), context("ca-q1-short", 1))
    rows = DeltaTable(str(path)).to_pandas()
    current = rows[rows["IS_CURRENT"]]
    assert len(current) == 5
    assert current["SUBMISSION_ID"].eq("ca-q1-short").sum() == 1
    assert not rows.loc[rows["SUBMISSION_ID"].eq("ca-q1"), "IS_CURRENT"].any()
    assert current.loc[current["SUBMISSION_ID"].eq("ca-q1-short"), "OBS_VALUE"].iloc[0] == Decimal("3.333")


def test_rejected_arrivals_preserve_prior_publication_and_each_identity(tmp_path):
    path = tmp_path / "history"
    merge_local_submission(path, batch(), context("good"))
    merge_local_submission(path, batch(rejected=True), context("bad-one", 1))
    merge_local_submission(path, batch(rejected=True), context("bad-two", 2))
    assert merge_local_submission(path, batch(rejected=True), context("bad-one", 1)) == 0
    rows = DeltaTable(str(path)).to_pandas()
    assert rows.loc[rows["IS_CURRENT"], "SUBMISSION_ID"].eq("good").all()
    assert len(rows[rows["BATCH_STATUS"].eq("QUARANTINE")]) == 4
    rejected = rows[rows["BATCH_STATUS"].eq("QUARANTINE")]
    assert rejected["VALID_FROM"].eq(rejected["VALID_TO"]).all()


def test_failed_transition_cannot_leave_expired_state_without_replacement(tmp_path):
    path = tmp_path / "history"
    merge_local_submission(path, batch(), context("first"))

    def fail():
        raise RuntimeError("Injected persistence failure")

    with pytest.raises(RuntimeError, match="Injected"):
        merge_local_submission(path, batch(values=("9.999",)), context("second", 1), before_commit=fail)
    table = DeltaTable(str(path))
    assert table.version() == 0
    assert table.to_pandas()["IS_CURRENT"].all()
    merge_local_submission(path, batch(values=("9.999",)), context("second", 1))
    assert DeltaTable(str(path)).version() == 1


def test_reused_identity_with_altered_content_is_rejected(tmp_path):
    path = tmp_path / "history"
    merge_local_submission(path, batch(), context("same"))
    with pytest.raises(ValueError, match="identity reused"):
        merge_local_submission(path, batch(values=("8.000",)), context("same"))
    assert DeltaTable(str(path)).version() == 0


def test_late_older_snapshot_is_audit_only(tmp_path):
    path = tmp_path / "history"
    merge_local_submission(path, batch(), context("newer", 2))
    merge_local_submission(path, batch(values=("9.000",)), context("older", 1))
    rows = DeltaTable(str(path)).to_pandas()
    assert rows.loc[rows["IS_CURRENT"], "SUBMISSION_ID"].eq("newer").all()
    assert len(rows) == 3


def test_concurrent_replay_has_one_logical_copy(tmp_path):
    path = tmp_path / "history"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: merge_local_submission(path, batch(), context("same")), range(2)))
    assert sorted(results) == [0, 2]
    assert len(DeltaTable(str(path)).to_pandas()) == 2


def test_duplicate_source_keys_are_refused(tmp_path):
    incoming = pd.concat([batch(), batch()], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate observation"):
        merge_local_submission(tmp_path / "history", incoming, context("duplicate"))


def test_spark_macro_has_one_commit_and_no_unprotected_creation():
    import ast
    import inspect
    from types import SimpleNamespace
    from spark_submission_history import merge_submission

    source = inspect.getsource(merge_submission)
    calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)]
    assert source.count("MERGE INTO") == 1
    assert sum(isinstance(node.func, ast.Attribute) and node.func.attr == "sql" for node in calls) == 1
    assert "createOrReplaceTempView" in source
    assert "dropTempView" in source
    assert "saveAsTable" not in source
    session = SimpleNamespace(catalog=SimpleNamespace(tableExists=lambda name: False))
    with pytest.raises(RuntimeError, match="Protected macro table is missing"):
        merge_submission(session, None, "history")


def test_legacy_local_entry_point_uses_atomic_replay(tmp_path):
    from local_pandas_scd2 import merge_scd2_micro_pandas

    frame = batch().assign(BANK_CODE="SYNTHETIC_BANK")
    path = str(tmp_path / "micro")
    merge_scd2_micro_pandas(frame, "ca", table_path=path)
    assert merge_scd2_micro_pandas(frame, "ca", table_path=path) == 0
    assert DeltaTable(path + "_ca").version() == 0