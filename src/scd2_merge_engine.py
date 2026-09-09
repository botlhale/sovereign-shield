"""
SCD2 Merge Engine (Project SovereignShield)
Handles Slowly Changing Dimension Type 2 (SCD2) MERGE logic and Scoped Logical Deletes 
for both sovereign micro-transaction tables and central macro history tables in Delta Lake / Unity Catalog.
"""

from typing import Dict, List

import glob
import os

import pandas as pd
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from delta.tables import DeltaTable
from delta import configure_spark_with_delta_pip
import datetime

from sdmx_rule_validator import DATA_DIR, SDMxRuleValidator

# Explicit schema for the validated macro batch: FAILED_RULE_ID is null for every row of a
# fully clean run, which Spark cannot type-infer from pandas on its own.
VALIDATED_MACRO_SCHEMA = StructType([
    StructField("TIME_SERIES_CODE", StringType(), False),
    StructField("DATE", StringType(), False),
    StructField("AGG_CODE", StringType(), False),
    StructField("OBS_VALUE", DoubleType(), True),
    StructField("OBS_STATUS", StringType(), True),
    StructField("OBS_CONF", StringType(), True),
    StructField("QUALITY_STATUS", StringType(), True),
    StructField("FAILED_RULE_ID", StringType(), True),
    StructField("BATCH_STATUS", StringType(), True),
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
    StructField("transaction_amount", DoubleType(), True),
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
        frames.append(pd.read_csv(path))
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
    arrival_label = cycle.rstrip("/").split("/")[-1].upper()

    ledger = pd.DataFrame(
        {
            # Deterministic from the filing rather than a UUID, so re-running a cycle
            # replays the same identities instead of inventing a new set each time.
            "transaction_id": [
                f"{arrival_label}_{row.L_REP_CTY}_{index:04d}"
                for index, row in enumerate(segments.itertuples(), start=1)
            ],
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
            "transaction_amount": raw["OBS_VALUE"].astype(float),
            # Carried down from the series the transaction fed, so the ledger records
            # which contributions ended up inside a restricted aggregate.
            "obs_conf": raw["TIME_SERIES_CODE"].map(obs_conf_by_series).fillna("F"),
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
    df_micro.write.format("delta").mode("append").option("mergeSchema", "true") \
        .saveAsTable("dbw_sovereignshield.sovereign_intake.lbs_micro_transactions")
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
    """
    Executes SCD2 Upsert and Scoped Logical Delete for Centralized Macro Data.
    Composite Key: TIME_SERIES_CODE, DATE, AGG_CODE

    Quarantined revisions never mutate active state. Rows arriving with
    BATCH_STATUS = 'QUARANTINE' are appended as IS_CURRENT = false audit records
    only: they do not expire, supersede, or logically delete the previously
    published version, so `v_agg_sdmx_published` keeps serving the last valid
    state for that reporting period. Only PUBLISHED rows drive the standard SCD2
    close-and-insert lifecycle.
    """
    payload_cols = ["OBS_VALUE", "OBS_STATUS", "OBS_CONF", "QUALITY_STATUS", "FAILED_RULE_ID", "BATCH_STATUS"]
    df_source = add_version_hash(df_incoming, payload_cols)

    df_published = df_source.filter(F.col("BATCH_STATUS") == "PUBLISHED")
    df_quarantined = df_source.filter(F.col("BATCH_STATUS") != "PUBLISHED")

    # 1. Initialize or load Delta Table
    # Column names must match the agg_sdmx_history DDL (unity_catalog_triple_lock.sql): VALID_FROM/VALID_TO/IS_CURRENT.
    if not spark.catalog.tableExists(target_table_name):
        df_init = df_source \
            .withColumn("VALID_FROM", F.current_timestamp()) \
            .withColumn("VALID_TO", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
            .withColumn("IS_CURRENT", F.col("BATCH_STATUS") == "PUBLISHED")
        df_init.write.format("delta").mode("overwrite").saveAsTable(target_table_name)
        print(f"Initialized new target table: {target_table_name}")
        return

    delta_target = DeltaTable.forName(spark, target_table_name)

    # Patch tables created before version-hash change tracking existed (e.g. via the DDL script).
    if "version_hash" not in delta_target.toDF().columns:
        spark.sql(f"ALTER TABLE {target_table_name} ADD COLUMNS (version_hash STRING)")

    # 2. Stage 1: Expire changed records (Match key, active status, but hash differs)
    join_key_cond = """
        target.TIME_SERIES_CODE = source.TIME_SERIES_CODE AND
        target.DATE = source.DATE AND
        target.AGG_CODE = source.AGG_CODE AND
        target.IS_CURRENT = true
    """

    delta_target.alias("target").merge(
        source=df_published.alias("source"),
        condition=join_key_cond
    ).whenMatchedUpdate(
        condition="target.version_hash != source.version_hash",
        set={
            "IS_CURRENT": "false",
            "VALID_TO": "current_timestamp()"
        }
    ).execute()

    # 3. Stage 2: Insert new active records (New keys OR superseded versions)
    active_target = delta_target.toDF().filter("IS_CURRENT = true")

    df_to_insert = df_published.alias("src").join(
        active_target.alias("tgt"),
        on=["TIME_SERIES_CODE", "DATE", "AGG_CODE"],
        how="left"
    ).filter(
        "tgt.TIME_SERIES_CODE IS NULL OR tgt.version_hash != src.version_hash"
    ).select("src.*") \
     .withColumn("VALID_FROM", F.current_timestamp()) \
     .withColumn("VALID_TO", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
     .withColumn("IS_CURRENT", F.lit(True))

    # Materialized so the count check and the write see one identical result set; the lazy
    # plan would otherwise re-read the table and could observe a concurrent commit.
    df_to_insert = df_to_insert.cache()
    insert_count = df_to_insert.count()
    if insert_count > 0:
        df_to_insert.write.format("delta").mode("append").saveAsTable(target_table_name)
        print(f"Inserted {insert_count} new active version(s).")
    df_to_insert.unpersist()

    # 4. Stage 2b: Append quarantined revisions as closed audit-only rows.
    # VALID_TO equals VALID_FROM so the row is never visible as an active version.
    # The anti-join keeps re-runs idempotent: replaying the same rejected submission must
    # not stack duplicate audit records.
    already_logged = delta_target.toDF().select("TIME_SERIES_CODE", "DATE", "AGG_CODE", "version_hash")

    df_quarantine_audit = df_quarantined.join(
        already_logged,
        on=["TIME_SERIES_CODE", "DATE", "AGG_CODE", "version_hash"],
        how="left_anti"
    ) \
        .withColumn("VALID_FROM", F.current_timestamp()) \
        .withColumn("VALID_TO", F.current_timestamp()) \
        .withColumn("IS_CURRENT", F.lit(False))

    df_quarantine_audit = df_quarantine_audit.cache()
    quarantined_count = df_quarantine_audit.count()
    if quarantined_count > 0:
        df_quarantine_audit.write.format("delta").mode("append").saveAsTable(target_table_name)
        print(
            f"Appended {quarantined_count} quarantined revision(s) as IS_CURRENT=false audit records; "
            "previously published versions remain active."
        )
    df_quarantine_audit.unpersist()

    # 5. Stage 3: Scoped Logical Delete
    # Expire active records within (DATE, AGG_CODE) scope missing from the incoming batch.
    # Restricted to reporting-period batches that actually published: a quarantined batch must
    # not retire its own previously published series just because the revision was rejected.
    published_batches = df_published.select(
        F.element_at(F.split(F.col("TIME_SERIES_CODE"), "\\."), 9).alias("REP_CTY"),
        F.col("DATE")
    ).distinct()

    df_incoming_keys = df_published.select("TIME_SERIES_CODE").distinct()

    # Re-read rather than reusing the pre-insert snapshot, otherwise rows written in Stage 2
    # would be treated as missing from the batch and immediately expired.
    deleted_keys = delta_target.toDF().filter(
        (F.col("IS_CURRENT") == True) & (F.col("DATE") == date_scope) & (F.col("AGG_CODE") == agg_scope)
    ).withColumn(
        "REP_CTY", F.element_at(F.split(F.col("TIME_SERIES_CODE"), "\\."), 9)
    ).join(
        published_batches, on=["REP_CTY", "DATE"], how="inner"
    ).join(
        df_incoming_keys,
        on="TIME_SERIES_CODE",
        how="left_anti"
    ).select("TIME_SERIES_CODE", "DATE", "AGG_CODE")

    deleted_keys = deleted_keys.cache()
    deleted_count = deleted_keys.count()
    if deleted_count > 0:
        delta_target.alias("target").merge(
            source=deleted_keys.alias("deleted"),
            condition="""
                target.TIME_SERIES_CODE = deleted.TIME_SERIES_CODE AND
                target.DATE = deleted.DATE AND
                target.AGG_CODE = deleted.AGG_CODE AND
                target.IS_CURRENT = true
            """
        ).whenMatchedUpdate(
            set={
                "IS_CURRENT": "false",
                "VALID_TO": "current_timestamp()"
            }
        ).execute()
        print(f"Logically deleted {deleted_count} missing records in scope ({date_scope}, {agg_scope}).")
    deleted_keys.unpersist()


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

    df_macro_final = spark.createDataFrame(
        # Records rather than the pandas frame itself. validator.validate() inherits
        # df_submitted's provenance as one CSV per country concatenated together,
        # which under pandas 3 backs each string column with a multi-chunk Arrow
        # ChunkedArray - the same shape createDataFrame cannot turn into a
        # RecordBatch that broke ingest_submitted_micro above.
        validator.validate(df_submitted).to_dict("records"),
        schema=VALIDATED_MACRO_SCHEMA,
    )

    # Log the verdict before committing. FAILED_RULE_ID names only the observations that
    # actually broke a check, so a quarantined batch shows its cause rather than a blanket.
    batch_summary = df_macro_final.withColumn(
        "REP_CTY", F.element_at(F.split(F.col("TIME_SERIES_CODE"), "\\."), 9)
    ).groupBy("REP_CTY", "DATE", "BATCH_STATUS").count()
    print(f"Macro batch routing for cycle '{cycle}' (atomic per country-quarter):")
    batch_summary.show(truncate=False)

    offenders = df_macro_final.filter(F.col("FAILED_RULE_ID").isNotNull())
    if offenders.count():
        print("Observations that failed a BIS consistency check:")
        offenders.select(
            "TIME_SERIES_CODE", "DATE", "OBS_VALUE", "FAILED_RULE_ID"
        ).show(truncate=False)

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