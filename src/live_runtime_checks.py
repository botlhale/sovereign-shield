"""Run bounded synthetic acceptance checks on the deployed Spark/Unity Catalog runtime."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pandas as pd
from pyspark.sql import SparkSession

from apply_security import parse_statements, resolve_sql_path, verify_existing_table_contracts, verify_policy_bindings, verify_policy_functions, version_policy_functions
from scd2_merge_engine import DATA_DIR, run_pipeline
from spark_submission_history import HISTORY_SCHEMA, merge_submission
from submission_history import TIME_COLUMNS, SubmissionContext, prepare_submission, stable_hash

HISTORY = "dbw_sovereignshield.sovereign_shield.agg_sdmx_history"
MICRO = "dbw_sovereignshield.sovereign_intake.lbs_micro_transactions"


def synthetic_batch(values=("1.111", "2.222"), *, country="CA", period="2026-Q1", rejected=False):
    return pd.DataFrame([{
        "TIME_SERIES_CODE": f"Q.S.C.A.USD.F.5J.A.{country}.{sector}.DE",
        "DATE": period, "AGG_CODE": "LBSR", "OBS_VALUE": value,
        "OBS_STATUS": "A", "OBS_CONF": "F", "QUALITY_STATUS": "FAIL" if rejected else "PASS",
        "BATCH_STATUS": "QUARANTINE" if rejected else "PUBLISHED",
        "FAILED_RULE_ID": "LBS_CC:04" if rejected and index == 0 else None,
        "BATCH_FAILED_RULE_ID": "LBS_CC:04" if rejected else None,
    } for index, (sector, value) in enumerate(zip(("B", "N"), values))])


def spark_batch(spark, identity, sequence, frame):
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=sequence)
    context = SubmissionContext(identity, stable_hash([identity]), instant, instant + timedelta(minutes=1))
    records = prepare_submission(frame, context).to_dict("records")
    for record in records:
        for name in TIME_COLUMNS:
            record[name] = None if pd.isna(record[name]) else pd.Timestamp(record[name]).to_pydatetime()
    return spark.createDataFrame(records, schema=HISTORY_SCHEMA)


def main():
    spark = SparkSession.builder.getOrCreate()
    statements, versions = version_policy_functions([
        statement for statement, _ in parse_statements(Path(resolve_sql_path()).read_text(encoding="utf-8"))
    ])
    verify_existing_table_contracts(spark)
    verify_policy_functions(spark, statements)
    verify_policy_bindings(spark, versions)
    before_macro = spark.table(HISTORY).count()
    before_micro = spark.table(MICRO).count()
    before_version = spark.sql(f"DESCRIBE HISTORY {HISTORY} LIMIT 1").first()["version"]
    run_pipeline(spark, submission_root=DATA_DIR)
    assert spark.table(HISTORY).count() == before_macro
    assert spark.table(MICRO).count() == before_micro
    assert spark.sql(f"DESCRIBE HISTORY {HISTORY} LIMIT 1").first()["version"] == before_version
    assert spark.table(HISTORY).filter("IS_CURRENT = true").count() == 22
    assert spark.table(HISTORY).filter("BATCH_STATUS = 'QUARANTINE' AND IS_CURRENT = true").count() == 0
    print("PASS deployed policy metadata, full-arrival replay and published-state preservation", flush=True)

    table = f"dbw_sovereignshield.sovereign_shield.acceptance_history_{uuid4().hex}"
    template = next(statement for statement in statements if statement.startswith("CREATE TABLE IF NOT EXISTS agg_sdmx_history"))
    spark.sql("USE CATALOG dbw_sovereignshield")
    spark.sql("USE SCHEMA sovereign_shield")
    spark.sql(template.replace("CREATE TABLE IF NOT EXISTS agg_sdmx_history", f"CREATE TABLE {table}", 1))
    try:
        def merge(identity, sequence, frame):
            merge_submission(spark, spark_batch(spark, identity, sequence, frame), table)

        merge("ca-first", 0, synthetic_batch())
        baseline_version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"]
        merge("ca-first", 0, synthetic_batch())
        assert spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"] == baseline_version
        merge("us-first", 0, synthetic_batch(country="US"))
        merge("ca-q2", 0, synthetic_batch(period="2026-Q2"))
        version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"]
        merge("ca-short", 1, synthetic_batch(values=("3.333",)))
        assert spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"] == version + 1
        rows = spark.table(table)
        assert rows.filter("IS_CURRENT = true").count() == 5
        assert rows.filter("SUBMISSION_ID = 'ca-first' AND IS_CURRENT = true").count() == 0
        assert rows.filter("SUBMISSION_ID = 'ca-short'").first()["OBS_VALUE"] == Decimal("3.333")
        merge("rejected-one", 2, synthetic_batch(values=("3.333",), rejected=True))
        merge("rejected-two", 3, synthetic_batch(values=("3.333",), rejected=True))
        assert spark.table(table).filter("BATCH_STATUS = 'QUARANTINE'").count() == 2
        assert spark.table(table).filter("IS_CURRENT = true").count() == 5
        merge("new-identical", 4, synthetic_batch(values=("3.333",)))
        assert spark.table(table).filter("SUBMISSION_ID = 'ca-short' AND IS_CURRENT = true").count() == 0
        merge("late-older", 1, synthetic_batch(values=("9.999",)))
        assert spark.table(table).filter("SUBMISSION_ID = 'late-older' AND IS_CURRENT = true").count() == 0
        version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"]
        for identity, frame in (("new-identical", synthetic_batch(values=("8.888",))), ("duplicate-source", pd.concat([synthetic_batch(), synthetic_batch()], ignore_index=True))):
            try:
                merge(identity, 5, frame)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid identity/source was accepted")
        assert spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"] == version
        assert spark.table(table).groupBy("RECORD_ID").count().filter("count > 1").count() == 0
        assert spark.table(table).filter("IS_CURRENT = true").groupBy("TIME_SERIES_CODE", "DATE", "AGG_CODE").count().filter("count > 1").count() == 0
        print("PASS actual UC Delta replay, one-commit replacement, scoped retirement, rejection audit, identity reuse and current-key uniqueness", flush=True)
    finally:
        spark.sql(f"DROP TABLE IF EXISTS {table}")
    print("LIVE_RUNTIME_ACCEPTANCE_PASSED", flush=True)


if __name__ == "__main__":
    main()