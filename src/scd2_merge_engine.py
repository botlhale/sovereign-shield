"""
SCD2 Merge Engine (Project SovereignShield)
Handles Slowly Changing Dimension Type 2 (SCD2) MERGE logic and Scoped Logical Deletes 
for both sovereign micro-transaction tables and central macro history tables in Delta Lake / Unity Catalog.
"""

from typing import List
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType
from delta.tables import DeltaTable
from delta import configure_spark_with_delta_pip
import datetime

from sdmx_rule_validator import SDMxRuleValidator

# Explicit schema for the validated macro batch: FAILED_RULE_ID is null for every row of a
# fully clean run, which Spark cannot type-infer from pandas on its own.
VALIDATED_MACRO_SCHEMA = StructType([
    StructField("TIME_SERIES_CODE", StringType(), False),
    StructField("DATE", StringType(), False),
    StructField("IBS_AGG", StringType(), False),
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
    "obs_conf", "ibs_agg_scope",
]


#: Full column order of the micro ledger. The synthetic row literals carry only the
#: leading business columns; the trailing batch columns are stamped by _build_micro_rows.
MICRO_SCHEMA = [
    "transaction_id", "reporting_country", "reporting_institution",
    "position_type", "instrument", "currency", "currency_type",
    "parent_country", "bank_type", "counterpart_country", "sector_code",
    "transaction_amount", "obs_conf", "ibs_agg_scope", "date_scope", "transaction_timestamp"
]

#: Batch-scoped columns appended to every row literal, in MICRO_SCHEMA order.
_BATCH_COLUMNS = ("ibs_agg_scope", "date_scope", "transaction_timestamp")


def _build_micro_rows(
    rows,
    ibs_agg_scope: str,
    date_scope: str,
    batch_timestamp: datetime.datetime,
):
    """Stamps every row of a submission batch with its shared batch-scoped columns.

    Calling datetime.now() per row produced a different VALID_FROM per record, so a
    single logical submission could not be reconstructed from the ledger.
    """
    expected_literal_width = len(MICRO_SCHEMA) - len(_BATCH_COLUMNS)
    for row in rows:
        if len(row) != expected_literal_width:
            raise ValueError(
                f"Micro row {row[0]!r} has {len(row)} values; expected "
                f"{expected_literal_width} before the batch columns {_BATCH_COLUMNS}."
            )
    return [row + (ibs_agg_scope, date_scope, batch_timestamp) for row in rows]


def generate_and_aggregate_micro_data(
    spark: SparkSession,
    date_scope: str = "2026-Q1",
    cycle: str = "baseline",
    ibs_agg_scope: str = "LBSR",
):
    """
    Simulates bank-level micro-transactions submitted by multiple country jurisdictions,
    carrying the full institutional attributes needed to build authentic BIS LBS
    SDMx dimension codes, and aggregates them into standardized SDMX observation series.

    Args:
        cycle: ``"baseline"`` emits a fully reconciling submission for every country.
            ``"revision"`` re-reports the same Canadian series keys with figures that
            break two BIS cross-checks, exercising the quarantine path against an
            already-published state.
    """
    if cycle not in ("baseline", "revision"):
        raise ValueError(f"cycle must be 'baseline' or 'revision', got {cycle!r}")

    batch_timestamp = datetime.datetime.now(datetime.timezone.utc)

    # Columns: transaction_id, reporting_country, reporting_institution, position_type,
    # instrument, currency, currency_type, parent_country, bank_type, counterpart_country,
    # sector_code, transaction_amount, obs_conf
    # Country codes are uppercase ISO 3166-1 alpha-2 so segment 9 of TIME_SERIES_CODE
    # matches the Unity Catalog RLS policy.
    #
    # Reconciliation groups use the real BIS aggregate codes (TO1 all currencies, 5J all
    # countries, A all sectors) so the dynamic checks have an aggregate to compare against.
    # They are isolated from the institutional rows, and from each other, by
    # position_type/instrument so no unintended cross-check context is shared.
    #
    # Observation values are signed: BIS LBS positions are legitimately negative as well as
    # positive. Zero-valued observations are not reported under SDMx convention and are
    # dropped after aggregation rather than being treated as an error.
    common_rows = [
        # Canada (CA) institutional positions
        ("TX_CA_001", "CA", "RBC_ROYAL_BANK", "C", "A", "CAD", "D", "CA", "A", "US", "B", 125000000.00, "F"),
        ("TX_CA_002", "CA", "TD_BANK_CA", "L", "D", "USD", "F", "CA", "D", "GB", "F", 45000000.00, "C"),
        ("TX_CA_003", "CA", "RBC_ROYAL_BANK", "C", "G", "EUR", "F", "CA", "A", "DE", "C", 89000000.00, "N"),

        # United States (US) institutional positions
        ("TX_US_001", "US", "JPMORGAN_US", "C", "A", "USD", "D", "US", "A", "CA", "B", 310000000.00, "F"),
        ("TX_US_002", "US", "CITI_US", "L", "D", "EUR", "F", "US", "D", "DE", "F", 89000000.00, "N"),
        ("TX_US_003", "US", "JPMORGAN_US", "C", "G", "GBP", "F", "US", "A", "GB", "C", 156000000.00, "F"),

        # United Kingdom (GB) institutional positions. TX_GB_002 is deliberately negative:
        # a net liability position is valid SDMx data and must publish cleanly.
        ("TX_GB_001", "GB", "BARCLAYS_UK", "C", "A", "GBP", "D", "GB", "A", "CA", "M", 210000000.00, "F"),
        ("TX_GB_002", "GB", "HSBC_UK", "L", "D", "CHF", "F", "GB", "B", "FR", "H", -67000000.00, "F"),
        ("TX_GB_003", "GB", "BARCLAYS_UK", "C", "G", "JPY", "F", "GB", "A", "JP", "G", 340000000.00, "C"),
    ]

    if cycle == "baseline":
        # Both Canadian reconciliation groups balance exactly, so the whole CA batch publishes.
        cycle_rows = [
            # LBS_CC01 group: TO1:A (139M) == CAD:D (50M) + TO1:F (89M).
            ("TX_CA_004", "CA", "RBC_ROYAL_BANK", "C", "B", "CAD", "D", "CA", "A", "5J", "B", 50000000.00, "F"),
            ("TX_CA_005", "CA", "RBC_ROYAL_BANK", "C", "B", "TO1", "F", "CA", "A", "5J", "B", 89000000.00, "F"),
            ("TX_CA_006", "CA", "RBC_ROYAL_BANK", "C", "B", "TO1", "A", "CA", "A", "5J", "B", 139000000.00, "F"),
            # LBS_CC:04 group: all sectors (500M) == banks (300M) + non-bank (200M).
            ("TX_CA_007", "CA", "TD_BANK_CA", "L", "A", "CHF", "D", "CA", "A", "5J", "A", 500000000.00, "F"),
            ("TX_CA_008", "CA", "TD_BANK_CA", "L", "A", "CHF", "D", "CA", "A", "5J", "B", 300000000.00, "F"),
            ("TX_CA_009", "CA", "TD_BANK_CA", "L", "A", "CHF", "D", "CA", "A", "5J", "N", 200000000.00, "F"),
        ]
    else:
        # Revised Canadian figures on the same series keys. The revision is arithmetically
        # inconsistent, so the atomic rule quarantines the entire CA country-quarter while the
        # baseline above stays IS_CURRENT = true.
        cycle_rows = [
            # LBS_CC01 breaks: -5M + 89M = 84M != the unchanged 139M aggregate. The negative
            # figure is valid SDMx data; the failure is the broken cross-check, not the sign.
            ("TX_CA_004", "CA", "RBC_ROYAL_BANK", "C", "B", "CAD", "D", "CA", "A", "5J", "B", -5000000.00, "F"),
            ("TX_CA_005", "CA", "RBC_ROYAL_BANK", "C", "B", "TO1", "F", "CA", "A", "5J", "B", 89000000.00, "F"),
            ("TX_CA_006", "CA", "RBC_ROYAL_BANK", "C", "B", "TO1", "A", "CA", "A", "5J", "B", 139000000.00, "F"),
            # LBS_CC:04 breaks: 300M + 150M = 450M != the unchanged 500M all-sectors total.
            ("TX_CA_007", "CA", "TD_BANK_CA", "L", "A", "CHF", "D", "CA", "A", "5J", "A", 500000000.00, "F"),
            ("TX_CA_008", "CA", "TD_BANK_CA", "L", "A", "CHF", "D", "CA", "A", "5J", "B", 300000000.00, "F"),
            ("TX_CA_009", "CA", "TD_BANK_CA", "L", "A", "CHF", "D", "CA", "A", "5J", "N", 150000000.00, "F"),
        ]

    raw_micro_data = _build_micro_rows(common_rows + cycle_rows, ibs_agg_scope, date_scope, batch_timestamp)

    df_micro = spark.createDataFrame(raw_micro_data, MICRO_SCHEMA)

    # Normalize casing before the key is built: a lowercase 'ca' would silently fall outside
    # the RLS predicate and make the row invisible to its own submitter.
    for column in UPPERCASE_MICRO_COLUMNS:
        df_micro = df_micro.withColumn(column, F.upper(F.trim(F.col(column))))

    _assert_valid_sector_codes(df_micro)

    # Write incoming micro transactions to Delta; mergeSchema evolves pre-existing tables
    # deployed before these institutional attribute columns were added.
    df_micro.write.format("delta").mode("append").option("mergeSchema", "true") \
        .saveAsTable("dbw_sovereignshield.sovereign_shield.lbs_micro_transactions")
    print(f"Multi-country micro transactions ingested successfully (cycle={cycle}).")

    # 2. Roll Up / Aggregate Micro Data into the full 11-dimension SDMX series key.
    # No wildcard placeholders: every BIS LBS dimension is sourced from real micro-data columns.
    df_aggregated = df_micro.groupBy(
            "position_type", "instrument", "currency", "currency_type",
            "parent_country", "bank_type", "reporting_country", "sector_code",
            "counterpart_country", "date_scope", "ibs_agg_scope"
        ) \
        .agg(
            F.sum("transaction_amount").alias("OBS_VALUE"),
            # If any transaction in the rollup is Confidential ('C'), elevate aggregate to 'C'
            F.when(F.array_contains(F.collect_set("obs_conf"), "C"), "C")
             .when(F.array_contains(F.collect_set("obs_conf"), "N"), "N")
             .otherwise("F").alias("OBS_CONF")
        ) \
        .withColumn(
            "TIME_SERIES_CODE",
            F.concat_ws(
                ".",
                F.lit("Q"),                      # FREQ (Quarterly)
                F.lit("S"),                      # L_MEASURE (Amounts outstanding)
                F.col("position_type"),          # L_POSITION
                F.col("instrument"),             # L_INSTR
                F.col("currency"),               # L_DENOM
                F.col("currency_type"),          # L_CURR_TYPE
                F.col("parent_country"),         # L_PARENT_CTY
                F.col("bank_type"),              # L_REP_BANK_TYPE
                F.col("reporting_country"),      # L_REP_CTY (segment 9 - RLS anchor)
                F.col("sector_code"),            # L_CP_SECTOR
                F.col("counterpart_country")     # L_CP_COUNTRY
            )
        ) \
        .withColumnRenamed("date_scope", "DATE") \
        .withColumnRenamed("ibs_agg_scope", "IBS_AGG") \
        .select("TIME_SERIES_CODE", "DATE", "IBS_AGG", "OBS_VALUE", "OBS_CONF")

    # SDMx convention: a zero position is simply not reported, so it must not be published
    # as an observation. Nulls are dropped for the same reason.
    df_aggregated = df_aggregated.filter(F.col("OBS_VALUE").isNotNull() & (F.col("OBS_VALUE") != 0))

    return df_aggregated


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
    target_table_name: str = "dbw_sovereignshield.sovereign_shield.lbs_sdmx_history",
    date_scope: str = "2026-Q1",
    ibs_agg_scope: str = "LBSR"
) -> None:
    """
    Executes SCD2 Upsert and Scoped Logical Delete for Centralized Macro Data.
    Composite Key: TIME_SERIES_CODE, DATE, IBS_AGG

    Quarantined revisions never mutate active state. Rows arriving with
    BATCH_STATUS = 'QUARANTINE' are appended as IS_CURRENT = false audit records
    only: they do not expire, supersede, or logically delete the previously
    published version, so `v_lbs_sdmx_published` keeps serving the last valid
    state for that country-quarter. Only PUBLISHED rows drive the standard SCD2
    close-and-insert lifecycle.
    """
    payload_cols = ["OBS_VALUE", "OBS_STATUS", "OBS_CONF", "QUALITY_STATUS", "FAILED_RULE_ID", "BATCH_STATUS"]
    df_source = add_version_hash(df_incoming, payload_cols)

    df_published = df_source.filter(F.col("BATCH_STATUS") == "PUBLISHED")
    df_quarantined = df_source.filter(F.col("BATCH_STATUS") != "PUBLISHED")

    # 1. Initialize or load Delta Table
    # Column names must match the lbs_sdmx_history DDL (unity_catalog_triple_lock.sql): VALID_FROM/VALID_TO/IS_CURRENT.
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
        target.IBS_AGG = source.IBS_AGG AND
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
        on=["TIME_SERIES_CODE", "DATE", "IBS_AGG"],
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
    already_logged = delta_target.toDF().select("TIME_SERIES_CODE", "DATE", "IBS_AGG", "version_hash")

    df_quarantine_audit = df_quarantined.join(
        already_logged,
        on=["TIME_SERIES_CODE", "DATE", "IBS_AGG", "version_hash"],
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
    # Expire active records within (DATE, IBS_AGG) scope missing from the incoming batch.
    # Restricted to country-quarter batches that actually published: a quarantined batch must
    # not retire its own previously published series just because the revision was rejected.
    published_batches = df_published.select(
        F.element_at(F.split(F.col("TIME_SERIES_CODE"), "\\."), 9).alias("REP_CTY"),
        F.col("DATE")
    ).distinct()

    df_incoming_keys = df_published.select("TIME_SERIES_CODE").distinct()

    # Re-read rather than reusing the pre-insert snapshot, otherwise rows written in Stage 2
    # would be treated as missing from the batch and immediately expired.
    deleted_keys = delta_target.toDF().filter(
        (F.col("IS_CURRENT") == True) & (F.col("DATE") == date_scope) & (F.col("IBS_AGG") == ibs_agg_scope)
    ).withColumn(
        "REP_CTY", F.element_at(F.split(F.col("TIME_SERIES_CODE"), "\\."), 9)
    ).join(
        published_batches, on=["REP_CTY", "DATE"], how="inner"
    ).join(
        df_incoming_keys,
        on="TIME_SERIES_CODE",
        how="left_anti"
    ).select("TIME_SERIES_CODE", "DATE", "IBS_AGG")

    deleted_keys = deleted_keys.cache()
    deleted_count = deleted_keys.count()
    if deleted_count > 0:
        delta_target.alias("target").merge(
            source=deleted_keys.alias("deleted"),
            condition="""
                target.TIME_SERIES_CODE = deleted.TIME_SERIES_CODE AND
                target.DATE = deleted.DATE AND
                target.IBS_AGG = deleted.IBS_AGG AND
                target.IS_CURRENT = true
            """
        ).whenMatchedUpdate(
            set={
                "IS_CURRENT": "false",
                "VALID_TO": "current_timestamp()"
            }
        ).execute()
        print(f"Logically deleted {deleted_count} missing records in scope ({date_scope}, {ibs_agg_scope}).")
    deleted_keys.unpersist()


def merge_scd2_micro(
    spark: SparkSession,
    df_incoming: DataFrame,
    country_code: str,
    target_catalog_schema: str = "dbw_sovereignshield.sovereign_shield",
    date_scope: str = "2026-Q1",
    ibs_agg_scope: str = "LBSR"
) -> None:
    """
    Executes SCD2 Upsert and Scoped Logical Delete for Sovereign Micro Transactions.
    Target Table: {target_catalog_schema}.lbs_micro_transactions_{country_code}
    Composite Key: TIME_SERIES_CODE, BANK_CODE, DATE, IBS_AGG
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
        target.IBS_AGG = source.IBS_AGG AND
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
        on=["TIME_SERIES_CODE", "BANK_CODE", "DATE", "IBS_AGG"],
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
        (F.col("DATE") == date_scope) & (F.col("IBS_AGG") == ibs_agg_scope)
    ).join(
        df_incoming_keys,
        on=["TIME_SERIES_CODE", "BANK_CODE"],
        how="left_anti"
    ).select("TIME_SERIES_CODE", "BANK_CODE", "DATE", "IBS_AGG")

    if deleted_keys.count() > 0:
        delta_target.alias("target").merge(
            source=deleted_keys.alias("deleted"),
            condition="""
                target.TIME_SERIES_CODE = deleted.TIME_SERIES_CODE AND
                target.BANK_CODE = deleted.BANK_CODE AND
                target.DATE = deleted.DATE AND
                target.IBS_AGG = deleted.IBS_AGG AND
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
    date_scope: str = "2026-Q1",
    ibs_agg_scope: str = "LBSR",
    cycle: str = "baseline"
) -> None:
    """Ingests synthetic micro-data, validates the aggregated macro batch, routes
    QUARANTINE/PUBLISHED records, and executes the SCD2 merge on the macro-history table.
    """
    # 1. Micro-data was already persisted to the append-only ledger inside this call.
    # DATE/IBS_AGG now come straight from the real aggregation grain; only OBS_STATUS
    # (an SDMx attribute, not a dimension) still needs a default.
    df_aggregated = generate_and_aggregate_micro_data(
        spark, date_scope=date_scope, cycle=cycle, ibs_agg_scope=ibs_agg_scope
    )
    df_aggregated = df_aggregated.withColumn("OBS_STATUS", F.lit("A"))

    # 2. Run the aggregated macro batch through the SDMx rule validation engine, which
    # assigns QUALITY_STATUS / FAILED_RULE_ID / BATCH_STATUS atomically per
    # (reporting country, reporting quarter) batch.
    validator = SDMxRuleValidator()
    df_macro_final = spark.createDataFrame(
        validator.validate(df_aggregated.toPandas()), schema=VALIDATED_MACRO_SCHEMA
    )

    # 3. Log PUBLISHED vs QUARANTINE volume before committing the merge.
    batch_summary = df_macro_final.withColumn(
        "REP_CTY", F.element_at(F.split(F.col("TIME_SERIES_CODE"), "\\."), 9)
    ).groupBy("REP_CTY", "DATE", "BATCH_STATUS", "FAILED_RULE_ID").count()
    print(f"Macro batch routing for cycle '{cycle}' (atomic per country-quarter):")
    batch_summary.show(truncate=False)

    # 4. SCD2 merge runs exclusively on the macro-history table.
    merge_scd2_macro(spark, df_macro_final, date_scope=date_scope, ibs_agg_scope=ibs_agg_scope)


def run_pipeline(
    spark: SparkSession,
    date_scope: str = "2026-Q1",
    ibs_agg_scope: str = "LBSR"
) -> None:
    """Runs the baseline submission followed by the revised submission.

    The two cycles exist so the SCD2 state machine is exercised end to end: the baseline
    publishes for every country, then Canada re-reports figures that fail the BIS
    cross-checks. The revision must be quarantined without disturbing the published
    baseline, which stays IS_CURRENT = true and continues to feed v_lbs_sdmx_published.
    """
    for cycle in ("baseline", "revision"):
        print(f"\n{'=' * 70}\nSubmission cycle: {cycle}\n{'=' * 70}")
        process_and_publish_macro_batch(
            spark, date_scope=date_scope, ibs_agg_scope=ibs_agg_scope, cycle=cycle
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