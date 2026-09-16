"""Atomic Spark/Delta transitions for the serialized ingestion job."""

import re
from uuid import uuid4

from delta.tables import DeltaTable
from pyspark.sql import functions as functions
from pyspark.sql.types import BooleanType, DecimalType, StringType, StructField, StructType, TimestampType

from submission_history import HISTORY_COLUMNS, STRING_COLUMNS, TIME_COLUMNS

HISTORY_SCHEMA = StructType(
    [StructField(name, StringType(), True) for name in STRING_COLUMNS]
    + [StructField("OBS_VALUE", DecimalType(38, 3), True)]
    + [StructField(name, TimestampType(), True) for name in TIME_COLUMNS]
    + [StructField("IS_CURRENT", BooleanType(), False)]
)


def merge_submission(spark, incoming, target_name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,2}", target_name):
        raise ValueError("Invalid target table identifier.")
    if not spark.catalog.tableExists(target_name):
        raise RuntimeError("Protected macro table is missing; run policy deployment first.")
    missing = set(HISTORY_COLUMNS) - set(incoming.columns)
    if missing:
        raise ValueError(f"Submission identity and validated history columns are required: {sorted(missing)}.")
    delta_target = DeltaTable.forName(spark, target_name)
    target = delta_target.toDF()
    if set(HISTORY_COLUMNS) - set(target.columns) or target.schema["OBS_VALUE"].dataType != DecimalType(38, 3):
        raise RuntimeError("Legacy macro history requires the explicit decimal/submission migration.")
    scope_columns = ["SUBMISSION_ID", "SOURCE_SHA256", "SUBMITTED_AT", "RECEIVED_AT", "DATE", "AGG_CODE", "BATCH_STATUS"]
    scopes = incoming.select(*scope_columns, functions.split("TIME_SERIES_CODE", r"\.").getItem(8).alias("country")).distinct().collect()
    if len(scopes) != 1:
        raise ValueError("Each atomic merge requires exactly one submission and country/period scope.")
    scope = scopes[0]
    if scope["BATCH_STATUS"] not in ("PUBLISHED", "QUARANTINE"):
        raise ValueError("Unsupported submission verdict.")
    if incoming.groupBy("TIME_SERIES_CODE", "DATE", "AGG_CODE").count().filter("count > 1").limit(1).count():
        raise ValueError("Duplicate observation in one submission.")
    prior = target.filter(functions.col("SUBMISSION_ID") == scope["SUBMISSION_ID"])
    if prior.limit(1).count():
        identity = ["RECORD_ID", "SOURCE_SHA256", "version_hash"]
        if prior.select(*identity).exceptAll(incoming.select(*identity)).limit(1).count() or incoming.select(*identity).exceptAll(prior.select(*identity)).limit(1).count():
            raise ValueError("Submission identity reused with different content or validation.")
        print(f"Replay skipped: {scope['SUBMISSION_ID']}")
        return
    target_scope = target.filter(
        (functions.split("TIME_SERIES_CODE", r"\.").getItem(8) == scope["country"])
        & (functions.col("DATE") == scope["DATE"]) & (functions.col("AGG_CODE") == scope["AGG_CODE"])
    )
    active = target_scope.filter(functions.col("IS_CURRENT"))
    if active.groupBy("TIME_SERIES_CODE", "DATE", "AGG_CODE").count().filter("count > 1").limit(1).count():
        raise RuntimeError("Existing history has duplicate current observations.")
    latest = target_scope.filter(functions.col("BATCH_STATUS") == "PUBLISHED").agg(functions.max("SUBMITTED_AT").alias("latest")).first()["latest"]
    publish = scope["BATCH_STATUS"] == "PUBLISHED" and (latest is None or scope["SUBMITTED_AT"] >= latest)
    inserts = incoming.select(*HISTORY_COLUMNS).withColumn("IS_CURRENT", functions.lit(publish)).withColumn(
        "VALID_TO", functions.lit(None).cast("timestamp") if publish else functions.col("RECEIVED_AT")
    ).withColumn("_operation", functions.lit("INSERT"))
    if publish:
        closes = active.select(*HISTORY_COLUMNS).withColumn("IS_CURRENT", functions.lit(False)).withColumn(
            "VALID_TO", functions.lit(scope["RECEIVED_AT"])
        ).withColumn("_operation", functions.lit("CLOSE"))
        staged = closes.unionByName(inserts)
    else:
        staged = inserts
    staging_view = f"submission_stage_{uuid4().hex}"
    staged.createOrReplaceTempView(staging_view)
    try:
        columns = ", ".join(f"`{name}`" for name in HISTORY_COLUMNS)
        values = ", ".join(f"source.`{name}`" for name in HISTORY_COLUMNS)
        spark.sql(
            f"MERGE INTO {target_name} AS target USING {staging_view} AS source "
            "ON target.RECORD_ID = source.RECORD_ID "
            "WHEN MATCHED AND source._operation = 'CLOSE' AND target.IS_CURRENT = true "
            "THEN UPDATE SET IS_CURRENT = false, VALID_TO = source.VALID_TO "
            "WHEN NOT MATCHED AND source._operation = 'INSERT' "
            f"THEN INSERT ({columns}) VALUES ({values})"
        )
    finally:
        spark.catalog.dropTempView(staging_view)
    print(f"Committed one atomic submission transition: {scope['SUBMISSION_ID']}")