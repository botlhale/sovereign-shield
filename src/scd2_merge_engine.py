"""
SCD2 Merge Engine (Project SovereignShield)
Handles Slowly Changing Dimension Type 2 (SCD2) MERGE logic and Scoped Logical Deletes 
for both sovereign micro-transaction tables and central macro history tables in Delta Lake / Unity Catalog.
"""

from typing import List
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from delta.tables import DeltaTable
from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
import datetime

from sdmx_rule_validator import SDMxRuleValidator

def generate_and_aggregate_micro_data(spark: SparkSession, date_scope: str = "2026-Q1"):
    """
    Simulates bank-level micro-transactions submitted by multiple country jurisdictions,
    carrying the full institutional attributes needed to build authentic BIS LBS
    SDMx dimension codes, and aggregates them into standardized SDMX observation series.
    """
    
    # 1. Generate Synthetic Multi-Country Micro Data
    # Columns: transaction_id, reporting_country, reporting_institution, position_type,
    # instrument, currency, currency_type, parent_country, bank_type, counterpart_country,
    # sector_code, transaction_amount, obs_conf, ibs_agg_scope, date_scope, transaction_timestamp
    raw_micro_data = [
        # Canada (ca) transactions
        ("TX_CA_001", "ca", "RBC_ROYAL_BANK", "C", "A", "CAD", "D", "CA", "A", "us", "B", 125000000.00, "F", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_CA_002", "ca", "TD_BANK_CA", "L", "D", "USD", "F", "CA", "D", "gb", "F", 45000000.00, "C", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_CA_003", "ca", "RBC_ROYAL_BANK", "C", "G", "EUR", "F", "CA", "A", "de", "C", 89000000.00, "N", "LBSR", date_scope, datetime.datetime.now()),

        # United States (us) transactions
        ("TX_US_001", "us", "JPMORGAN_US", "C", "A", "USD", "D", "US", "A", "ca", "B", 310000000.00, "F", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_US_002", "us", "CITI_US", "L", "D", "EUR", "F", "US", "D", "de", "F", 89000000.00, "N", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_US_003", "us", "JPMORGAN_US", "C", "G", "GBP", "F", "US", "A", "gb", "C", 156000000.00, "F", "LBSR", date_scope, datetime.datetime.now()),

        # United Kingdom (gb) transactions
        ("TX_GB_001", "gb", "BARCLAYS_UK", "C", "A", "GBP", "D", "GB", "A", "ca", "M", 210000000.00, "F", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_GB_002", "gb", "HSBC_UK", "L", "D", "CHF", "F", "GB", "B", "fr", "H", 67000000.00, "F", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_GB_003", "gb", "BARCLAYS_UK", "C", "G", "JPY", "F", "GB", "A", "jp", "G", 340000000.00, "C", "LBSR", date_scope, datetime.datetime.now())
    ]
    
    schema = [
        "transaction_id", "reporting_country", "reporting_institution",
        "position_type", "instrument", "currency", "currency_type",
        "parent_country", "bank_type", "counterpart_country", "sector_code",
        "transaction_amount", "obs_conf", "ibs_agg_scope", "date_scope", "transaction_timestamp"
    ]
    
    df_micro = spark.createDataFrame(raw_micro_data, schema)
    
    # Write incoming micro transactions to Delta; mergeSchema evolves pre-existing tables
    # deployed before these institutional attribute columns were added.
    df_micro.write.format("delta").mode("append").option("mergeSchema", "true") \
        .saveAsTable("dbw_sovereignshield.sovereign_shield.lbs_micro_transactions")
    print("Multi-country micro transactions ingested successfully.")

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
        
    return df_aggregated

def add_version_hash(df: DataFrame, payload_cols: List[str]) -> DataFrame:
    """Calculates SHA256 version hash across payload columns to detect updates."""
    concat_expr = F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("")) for c in payload_cols])
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
    """
    payload_cols = ["OBS_VALUE", "OBS_STATUS", "OBS_CONF", "QUALITY_STATUS", "FAILED_RULE_ID", "BATCH_STATUS"]
    df_source = add_version_hash(df_incoming, payload_cols)

    # 1. Initialize or load Delta Table
    # Column names must match the lbs_sdmx_history DDL (unity_catalog_triple_lock.sql): VALID_FROM/VALID_TO/IS_CURRENT.
    if not spark.catalog.tableExists(target_table_name):
        df_init = df_source \
            .withColumn("VALID_FROM", F.current_timestamp()) \
            .withColumn("VALID_TO", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
            .withColumn("IS_CURRENT", F.lit(True))
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
        source=df_source.alias("source"),
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
    
    df_to_insert = df_source.alias("src").join(
        active_target.alias("tgt"),
        on=["TIME_SERIES_CODE", "DATE", "IBS_AGG"],
        how="left"
    ).filter(
        "tgt.TIME_SERIES_CODE IS NULL OR tgt.version_hash != src.version_hash"
    ).select("src.*") \
     .withColumn("VALID_FROM", F.current_timestamp()) \
     .withColumn("VALID_TO", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
     .withColumn("IS_CURRENT", F.lit(True))

    if df_to_insert.count() > 0:
        df_to_insert.write.format("delta").mode("append").saveAsTable(target_table_name)

    # 4. Stage 3: Scoped Logical Delete
    # Expire active records within (DATE, IBS_AGG) scope missing from incoming batch
    df_incoming_keys = df_source.select("TIME_SERIES_CODE").distinct()
    
    deleted_keys = active_target.filter(
        (F.col("DATE") == date_scope) & (F.col("IBS_AGG") == ibs_agg_scope)
    ).join(
        df_incoming_keys,
        on="TIME_SERIES_CODE",
        how="left_anti"
    ).select("TIME_SERIES_CODE", "DATE", "IBS_AGG")

    if deleted_keys.count() > 0:
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
        print(f"Logically deleted {deleted_keys.count()} missing records in scope ({date_scope}, {ibs_agg_scope}).")


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
    ibs_agg_scope: str = "LBSR"
) -> None:
    """Ingests synthetic micro-data, validates the aggregated macro batch, routes
    QUARANTINE/PUBLISHED records, and executes the SCD2 merge on the macro-history table.
    """
    # 1. Micro-data was already persisted to the append-only ledger inside this call.
    # DATE/IBS_AGG now come straight from the real aggregation grain; only OBS_STATUS
    # (an SDMx attribute, not a dimension) still needs a default.
    df_aggregated = generate_and_aggregate_micro_data(spark, date_scope=date_scope)
    df_aggregated = df_aggregated.withColumn("OBS_STATUS", F.lit("A"))

    # 2. Run the aggregated macro batch through the SDMx rule validation engine.
    validator = SDMxRuleValidator()
    df_validated = spark.createDataFrame(validator.validate(df_aggregated.toPandas()))

    # 3. Quarantine routing: row-level BATCH_STATUS derived from the validation outcome.
    df_macro_final = df_validated.withColumn(
        "BATCH_STATUS",
        F.when(F.col("QUALITY_STATUS") == "FAIL", F.lit("QUARANTINE")).otherwise(F.lit("PUBLISHED"))
    )

    # 5. Log PUBLISHED vs QUARANTINE volume before committing the merge.
    published_count = df_macro_final.filter(F.col("BATCH_STATUS") == "PUBLISHED").count()
    quarantine_count = df_macro_final.filter(F.col("BATCH_STATUS") == "QUARANTINE").count()
    print(f"Macro batch routing -> PUBLISHED: {published_count} | QUARANTINE: {quarantine_count}")

    # 4. SCD2 merge runs exclusively on the macro-history table.
    merge_scd2_macro(spark, df_macro_final, date_scope=date_scope, ibs_agg_scope=ibs_agg_scope)


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
    process_and_publish_macro_batch(spark)