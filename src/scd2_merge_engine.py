"""
SCD2 Merge Engine (Project SovereignShield)
Handles Slowly Changing Dimension Type 2 (SCD2) MERGE logic and Scoped Logical Deletes 
for both sovereign micro-transaction tables and central macro history tables in Delta Lake / Unity Catalog.
"""

from typing import Dict, List

import glob
import hashlib
import os

import pandas as pd
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DecimalType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from delta.tables import DeltaTable
from delta import configure_spark_with_delta_pip
import datetime

from sdmx_rule_validator import DATA_DIR, SDMxRuleValidator
from decimal_measures import decimal_value
from spark_submission_history import HISTORY_SCHEMA
from submission_history import TIME_COLUMNS, SubmissionContext, prepare_submission, stable_hash

# Explicit schema for the validated macro batch: FAILED_RULE_ID is null for every row of a
# fully clean run, which Spark cannot type-infer from pandas on its own.
VALIDATED_MACRO_SCHEMA = StructType([
    StructField("TIME_SERIES_CODE", StringType(), False),
    StructField("DATE", StringType(), False),
    StructField("AGG_CODE", StringType(), False),
    StructField("OBS_VALUE", DecimalType(38, 3), True),
    StructField("OBS_STATUS", StringType(), True),
    StructField("OBS_CONF", StringType(), True),
    StructField("QUALITY_STATUS", StringType(), True),
    StructField("FAILED_RULE_ID", StringType(), True),
    StructField("BATCH_STATUS", StringType(), True),
    StructField("BATCH_FAILED_RULE_ID", StringType(), True),
    StructField("VALIDATION_NOTES", StringType(), True),
])

#: BIS LBS counterparty sector codelist. B/M/F/C/G/H are the reported institutional
#: breakdowns; A (all sectors), N (non-bank sector) and U (unallocated) are the standard
#: BIS aggregate codes the consistency checks reconcile against. Anything outside this set
#: is a non-standard placeholder and is rejected before it can reach Unity Catalog.
VALID_SECTOR_CODES = {"B", "M", "F", "C", "G", "H", "A", "N", "U"}

#: Columns normalized to uppercase so the SDMx key, and therefore the RLS predicate on
#: segment 9, can never be defeated by a casing mismatch in an upstream feed.
UPPERCASE_MICRO_COLUMNS = [
    "reporting_country", "position_type", "instrument", "currency", "currency_type",
    "parent_country", "bank_type", "counterpart_country", "sector_code",
    "obs_conf", "agg_scope",
]


#: Micro ledger schema, matching the DDL in unity_catalog_triple_lock.sql. Declared
#: rather than inferred: an all-null column in one arrival would otherwise be typed
#: from that batch and disagree with the table it is appended to.
MICRO_STRUCT = StructType([
    StructField("transaction_id", StringType(), True),
    StructField("reporting_country", StringType(), True),
    StructField("reporting_institution", StringType(), True),
    StructField("position_type", StringType(), True),
    StructField("instrument", StringType(), True),
    StructField("currency", StringType(), True),
    StructField("currency_type", StringType(), True),
    StructField("parent_country", StringType(), True),
    StructField("bank_type", StringType(), True),
    StructField("counterpart_country", StringType(), True),
    StructField("sector_code", StringType(), True),
    StructField("transaction_amount", DecimalType(38, 3), True),
    StructField("obs_conf", StringType(), True),
    StructField("agg_scope", StringType(), True),
    StructField("date_scope", StringType(), True),
    StructField("transaction_timestamp", TimestampType(), True),
])

#: Full column order of the micro ledger.
MICRO_SCHEMA = [field.name for field in MICRO_STRUCT.fields]

#: The 11 BIS_LBS dimensions in TIME_SERIES_CODE order. The submitted key is the only
#: place the institutional attributes survive, so the ledger is rebuilt by splitting it.
DSD_SEGMENTS = [
    "FREQ", "L_MEASURE", "L_POSITION", "L_INSTR", "L_DENOM", "L_CURR_TYPE",
    "L_PARENT_CTY", "L_REP_BANK_TYPE", "L_REP_CTY", "L_CP_SECTOR", "L_CP_COUNTRY"
]


def ingest_submitted_micro(
    spark: SparkSession,
    submission_dir: str,
    obs_conf_by_series: Dict[str, str],
    cycle: str = "baseline",
) -> None:
    """Appends the bank-level micro-data filed alongside a submission to the ledger.

    The ledger is evidence, not input. It shows how each reporting body arrived at
    its confidentiality decision - which institution contributed what to a series
    that ended up restricted - and it is the table the micro row filter isolates
    by ``reporting_country``. Nothing downstream re-derives the macro figures from
    it: the receiving organisation rules on the series the country actually
    submitted, not on a recomputation of them.

    Read through pandas rather than ``spark.read.csv`` because the files are local
    to the driver; a Spark reader would ask executors for a path only the driver
    can see.
    """
    batch_timestamp = datetime.datetime.now(datetime.timezone.utc)

    frames = []
    for path in sorted(glob.glob(os.path.join(submission_dir, "micro_transactions_*.csv"))):
        raw_frame = pd.read_csv(path, dtype={"OBS_VALUE": "string"})
        with open(path, "rb") as source:
            digest = hashlib.sha256(source.read()).hexdigest()
        file_identity = stable_hash([os.path.normpath(os.path.abspath(path)), digest])
        raw_frame["_transaction_id"] = [stable_hash([file_identity, index]) for index in range(len(raw_frame))]
        frames.append(raw_frame)
    if not frames:
        raise FileNotFoundError(
            f"No micro-data accompanying the submissions in {submission_dir!r}."
        )

    raw = pd.concat(frames, ignore_index=True)
    segments = raw["TIME_SERIES_CODE"].str.split(".", expand=True)
    if segments.shape[1] != len(DSD_SEGMENTS):
        raise ValueError(
            f"Micro-data keys have {segments.shape[1]} segments; expected "
            f"{len(DSD_SEGMENTS)} ({', '.join(DSD_SEGMENTS)})."
        )
    segments.columns = DSD_SEGMENTS

    # cycle is the arrival's path under the volume; only its leaf belongs in an identifier.
    ledger = pd.DataFrame(
        {
            # Deterministic from the filing rather than a UUID, so re-running a cycle
            # replays the same identities instead of inventing a new set each time.
            "transaction_id": raw["_transaction_id"],
            "reporting_country": segments["L_REP_CTY"],
            "reporting_institution": raw["BANK_CODE"],
            "position_type": segments["L_POSITION"],
            "instrument": segments["L_INSTR"],
            "currency": segments["L_DENOM"],
            "currency_type": segments["L_CURR_TYPE"],
            "parent_country": segments["L_PARENT_CTY"],
            "bank_type": segments["L_REP_BANK_TYPE"],
            "counterpart_country": segments["L_CP_COUNTRY"],
            "sector_code": segments["L_CP_SECTOR"],
            "transaction_amount": raw["OBS_VALUE"].map(decimal_value),
            # Carried down from the series the transaction fed, so the ledger records
            # which contributions ended up inside a restricted aggregate.
            "obs_conf": raw["TIME_SERIES_CODE"].map(obs_conf_by_series).fillna("N"),
            "agg_scope": raw["AGG_CODE"],
            "date_scope": raw["DATE"],
            "transaction_timestamp": batch_timestamp,
        }
    )

    # Built from records rather than handed to Spark as a pandas frame. pandas backs
    # string columns with Arrow arrays, and concatenating one CSV per country yields a
    # multi-chunk ChunkedArray that Spark's pandas-to-Arrow path cannot turn into a
    # RecordBatch. A filing is a few thousand rows at most, so the cost is nil.
    records = ledger[MICRO_SCHEMA].to_dict("records")

    # Restored from the original scalar because pandas promotes a datetime column to
    # pandas.Timestamp, and Spark's verifier matches on exact type rather than
    # isinstance - so a subclass of datetime is refused.
    for record in records:
        record["transaction_timestamp"] = batch_timestamp

    df_micro = spark.createDataFrame(records, schema=MICRO_STRUCT)

    # Normalize casing before the key is built: a lowercase 'ca' would silently fall outside
    # the RLS predicate and make the row invisible to its own submitter.
    for column in UPPERCASE_MICRO_COLUMNS:
        df_micro = df_micro.withColumn(column, F.upper(F.trim(F.col(column))))

    _assert_valid_sector_codes(df_micro)

    # Write incoming micro transactions to Delta; mergeSchema evolves pre-existing tables
    # deployed before these institutional attribute columns were added.
    target = "dbw_sovereignshield.sovereign_intake.lbs_micro_transactions"
    if not spark.catalog.tableExists(target):
        raise RuntimeError("Protected micro table is missing; run policy deployment first.")
    DeltaTable.forName(spark, target).alias("target").merge(
        df_micro.alias("source"), "target.transaction_id = source.transaction_id"
    ).whenNotMatchedInsertAll().execute()
    print(f"Multi-country micro transactions ingested successfully (cycle={cycle}).")


def _assert_valid_sector_codes(df_micro: DataFrame) -> None:
    """Fails the batch if any counterparty sector falls outside the BIS codelist."""
    offenders = df_micro.filter(~F.col("sector_code").isin(list(VALID_SECTOR_CODES))) \
        .select("sector_code").distinct().collect()
    if offenders:
        codes = sorted(row["sector_code"] for row in offenders)
        raise ValueError(
            f"Non-standard L_CP_SECTOR code(s) {codes}; permitted BIS codes are "
            f"{sorted(VALID_SECTOR_CODES)}."
        )


def add_version_hash(df: DataFrame, payload_cols: List[str]) -> DataFrame:
    """Calculates SHA256 version hash across payload columns to detect updates.

    NULL is encoded with a sentinel rather than an empty string so that a cleared
    FAILED_RULE_ID cannot hash identically to one that was never populated.
    """
    concat_expr = F.concat_ws(
        "||", *[F.coalesce(F.col(c).cast("string"), F.lit("\u0000NULL")) for c in payload_cols]
    )
    return df.withColumn("version_hash", F.sha2(concat_expr, 256))


def merge_scd2_macro(
    spark: SparkSession,
    df_incoming: DataFrame,
    target_table_name: str = "dbw_sovereignshield.sovereign_shield.agg_sdmx_history",
    date_scope: str = "2026-Q1",
    agg_scope: str = "LBSR"
) -> None:
    """Atomically commit one prepared full-snapshot submission; scope comes from the rows."""
    from spark_submission_history import merge_submission

    merge_submission(spark, df_incoming, target_table_name)


def merge_scd2_micro(
    spark: SparkSession,
    df_incoming: DataFrame,
    country_code: str,
    target_catalog_schema: str = "dbw_sovereignshield.sovereign_shield",
    date_scope: str = "2026-Q1",
    agg_scope: str = "LBSR"
) -> None:
    """
    Executes SCD2 Upsert and Scoped Logical Delete for Sovereign Micro Transactions.
    Target Table: {target_catalog_schema}.lbs_micro_transactions_{country_code}
    Composite Key: TIME_SERIES_CODE, BANK_CODE, DATE, AGG_CODE
    """
    table_name = f"{target_catalog_schema}.lbs_micro_transactions_{country_code.lower()}"
    payload_cols = ["OBS_VALUE"]
    df_source = add_version_hash(df_incoming, payload_cols)

    if not spark.catalog.tableExists(table_name):
        df_init = df_source \
            .withColumn("effective_start_date", F.current_timestamp()) \
            .withColumn("effective_end_date", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
            .withColumn("is_current", F.lit(True))
        df_init.write.format("delta").mode("overwrite").saveAsTable(table_name)
        print(f"Initialized micro table: {table_name}")
        return

    delta_target = DeltaTable.forName(spark, table_name)

    join_key_cond = """
        target.TIME_SERIES_CODE = source.TIME_SERIES_CODE AND
        target.BANK_CODE = source.BANK_CODE AND
        target.DATE = source.DATE AND
        target.AGG_CODE = source.AGG_CODE AND
        target.is_current = true
    """

    # Stage 1: Expire changed
    delta_target.alias("target").merge(
        source=df_source.alias("source"),
        condition=join_key_cond
    ).whenMatchedUpdate(
        condition="target.version_hash != source.version_hash",
        set={
            "is_current": "false",
            "effective_end_date": "current_timestamp()"
        }
    ).execute()

    # Stage 2: Insert new/updated
    active_target = delta_target.toDF().filter("is_current = true")
    
    df_to_insert = df_source.alias("src").join(
        active_target.alias("tgt"),
        on=["TIME_SERIES_CODE", "BANK_CODE", "DATE", "AGG_CODE"],
        how="left"
    ).filter(
        "tgt.TIME_SERIES_CODE IS NULL OR tgt.version_hash != src.version_hash"
    ).select("src.*") \
     .withColumn("effective_start_date", F.current_timestamp()) \
     .withColumn("effective_end_date", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
     .withColumn("is_current", F.lit(True))

    if df_to_insert.count() > 0:
        df_to_insert.write.format("delta").mode("append").saveAsTable(table_name)

    # Stage 3: Scoped Logical Delete
    df_incoming_keys = df_source.select("TIME_SERIES_CODE", "BANK_CODE").distinct()
    
    deleted_keys = active_target.filter(
        (F.col("DATE") == date_scope) & (F.col("AGG_CODE") == agg_scope)
    ).join(
        df_incoming_keys,
        on=["TIME_SERIES_CODE", "BANK_CODE"],
        how="left_anti"
    ).select("TIME_SERIES_CODE", "BANK_CODE", "DATE", "AGG_CODE")

    if deleted_keys.count() > 0:
        delta_target.alias("target").merge(
            source=deleted_keys.alias("deleted"),
            condition="""
                target.TIME_SERIES_CODE = deleted.TIME_SERIES_CODE AND
                target.BANK_CODE = deleted.BANK_CODE AND
                target.DATE = deleted.DATE AND
                target.AGG_CODE = deleted.AGG_CODE AND
                target.is_current = true
            """
        ).whenMatchedUpdate(
            set={
                "is_current": "false",
                "effective_end_date": "current_timestamp()"
            }
        ).execute()


def process_and_publish_macro_batch(
    spark: SparkSession,
    submission_dir: str,
    date_scope: str = "2026-Q1",
    agg_scope: str = "LBSR",
    cycle: str = "baseline",
) -> None:
    """Receives one cycle of sovereign submissions, rules on them, and versions the result.

    This is the receiving organisation's side of the exchange. It reads the SDMx-ML
    files the reporting bodies filed, re-runs the BIS consistency checks over them,
    and decides publication independently. The submitting country will have run the
    same workbook before filing; agreeing with it is not assumed.

    The submitted observations are validated as filed. They are deliberately not
    re-derived from the accompanying micro-data: a hub that recomputes the figures
    is checking its own arithmetic, not the submission.
    """
    validator = SDMxRuleValidator()
    submissions = validator.load_submissions(submission_dir)
    if not submissions:
        raise FileNotFoundError(
            f"No SDMx submissions found in {submission_dir!r}. The reporting task "
            f"writes them there; check SOVEREIGNSHIELD_SUBMISSION_DIR is the same "
            f"for both tasks."
        )
    print(
        f"Received {len(submissions)} sovereign submission(s) from "
        f"{', '.join(sorted(code.upper() for code in submissions))}."
    )

    df_submitted = pd.concat(submissions.values(), ignore_index=True)

    # The ledger records how each country reached its confidentiality decision, keyed
    # by the series that decision applies to.
    ingest_submitted_micro(
        spark,
        submission_dir,
        obs_conf_by_series=dict(
            zip(df_submitted["TIME_SERIES_CODE"], df_submitted["OBS_CONF"])
        ),
        cycle=cycle,
    )

    # OBS_STATUS is an SDMx attribute rather than a dimension; absent means normal.
    df_submitted["OBS_STATUS"] = df_submitted["OBS_STATUS"].fillna("A")

    ordered = sorted(submissions.values(), key=lambda frame: (frame.attrs["SUBMITTED_AT"], frame.attrs["SUBMISSION_ID"]))
    for submitted in ordered:
        validated = validator.validate(submitted)
        context = SubmissionContext(
            submitted.attrs["SUBMISSION_ID"], submitted.attrs["SOURCE_SHA256"],
            submitted.attrs["SUBMITTED_AT"].to_pydatetime(), datetime.datetime.now(datetime.timezone.utc),
        )
        prepared = prepare_submission(validated, context)
        records = prepared.to_dict("records")
        for record in records:
            for name in TIME_COLUMNS:
                record[name] = None if pd.isna(record[name]) else pd.Timestamp(record[name]).to_pydatetime()
        df_macro_final = spark.createDataFrame(records, schema=HISTORY_SCHEMA)
        merge_scd2_macro(spark, df_macro_final, date_scope=date_scope, agg_scope=agg_scope)


def run_pipeline(
    spark: SparkSession,
    submission_root: str = DATA_DIR,
    date_scope: str = "2026-Q1",
    agg_scope: str = "LBSR",
) -> None:
    """Processes each filed cycle in the order it was received.

    The two cycles exist so the SCD2 state machine is exercised end to end: every
    country publishes on the baseline, then each re-reports figures that break a BIS
    cross-check. The revision must be quarantined without disturbing the published
    baseline, which stays IS_CURRENT = true and continues to feed v_agg_sdmx_published.
    """
    if not os.path.isdir(submission_root):
        raise FileNotFoundError(
            f"No submission root at {submission_root!r}. The reporting task writes it; "
            f"check SOVEREIGNSHIELD_SUBMISSION_DIR is the same for both tasks."
        )

    # Arrivals are discovered rather than enumerated, so the layout can carry whatever
    # collection and date hierarchy the filings need. Sorting the full path yields filing
    # order because every component is zero-padded and ordered coarse to fine:
    # <family>/<dataset>/<yyyy>/<mm>/<dd>/<NN>_<cycle>. A hub replaying arrivals out of
    # order would expire a live version against a submission that predates it.
    arrivals = sorted({
        os.path.dirname(path)
        for path in glob.glob(
            os.path.join(submission_root, "**", "*_submission*.xml"), recursive=True
        )
    })
    if not arrivals:
        raise FileNotFoundError(f"No submissions filed under {submission_root!r}.")

    for cycle_dir in arrivals:
        cycle = os.path.relpath(cycle_dir, submission_root).replace(os.sep, "/")
        print(f"\n{'=' * 70}\nSubmission arrival: {cycle}\n{'=' * 70}")
        process_and_publish_macro_batch(
            spark, cycle_dir, date_scope=date_scope, agg_scope=agg_scope, cycle=cycle
        )


# if __name__ == "__main__":
#     spark_session = SparkSession.builder \
#         .appName("SCD2MergeEngineTest") \
#         .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
#         .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
#         .getOrCreate()
    
#     print("SCD2 Merge Engine loaded successfully.")

if __name__ == "__main__":
    builder = SparkSession.builder \
        .appName("SCD2MergeEngineTest") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    
    # This automatically downloads the required Delta Lake JARs
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    
    print("SCD2 Merge Engine loaded successfully with Delta Lake.")
    run_pipeline(spark)