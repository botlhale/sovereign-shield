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

def generate_and_aggregate_micro_data(spark: SparkSession, date_scope: str = "2026-Q1"):
    """
    Simulates micro-transactions submitted by multiple country jurisdictions
    and aggregates them into standardized SDMX observation series.
    """
    
    # 1. Generate Synthetic Multi-Country Micro Data
    raw_micro_data = [
        # Canada (ca) transactions
        ("TX_CA_001", "ca", "BOC_INST_01", "us", "FC", "CAD", 1250000.00, "F", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_CA_002", "ca", "BOC_INST_02", "gb", "NFC", "USD", 450000.00, "C", "LBSR", date_scope, datetime.datetime.now()),
        
        # United States (us) transactions
        ("TX_US_001", "us", "FED_INST_01", "ca", "FC", "USD", 3100000.00, "F", "LBSR", date_scope, datetime.datetime.now()),
        ("TX_US_002", "us", "FED_INST_03", "de", "NFC", "EUR", 890000.00, "N", "LBSR", date_scope, datetime.datetime.now()),
        
        # United Kingdom (gb) transactions
        ("TX_GB_001", "gb", "BOE_INST_01", "ca", "FC", "GBP", 2100000.00, "F", "LBSR", date_scope, datetime.datetime.now())
    ]
    
    schema = [
        "transaction_id", "reporting_country", "reporting_institution", 
        "counterpart_country", "sector_code", "currency", 
        "transaction_amount", "obs_conf", "ibs_agg_scope", "date_scope", "transaction_timestamp"
    ]
    
    df_micro = spark.createDataFrame(raw_micro_data, schema)
    
    # Write incoming micro transactions to Delta
    df_micro.write.format("delta").mode("append").saveAsTable("dbw_sovereignshield.sovereign_shield.lbs_micro_transactions")
    print("Multi-country micro transactions ingested successfully.")

    # 2. Roll Up / Aggregate Micro Data into SDMX Series Key Dimensions
    # Builds an SDMX dimension key format: e.g., 'BIS.LBS.S.A.<SCOPE>.<CURRENCY>.<COUNTRY>'
    df_aggregated = df_micro.groupBy("reporting_country", "ibs_agg_scope", "currency", "date_scope") \
        .agg(
            F.sum("transaction_amount").alias("OBS_VALUE"),
            # If any transaction in the rollup is Confidential ('C'), elevate aggregate to 'C'
            F.when(F.array_contains(F.collect_set("obs_conf"), "C"), "C")
             .when(F.array_contains(F.collect_set("obs_conf"), "N"), "N")
             .otherwise("F").alias("OBS_CONF")
        ) \
        .withColumn(
            "TIME_SERIES_CODE", 
            F.concat_ws(".", F.lit("BIS.LBS.S.A"), F.col("ibs_agg_scope"), F.col("currency"), F.col("reporting_country"))
        ) \
        .select("TIME_SERIES_CODE", "OBS_VALUE", "OBS_CONF")
        
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
    if not spark.catalog.tableExists(target_table_name):
        df_init = df_source \
            .withColumn("effective_start_date", F.current_timestamp()) \
            .withColumn("effective_end_date", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
            .withColumn("is_current", F.lit(True))
        df_init.write.format("delta").mode("overwrite").saveAsTable(target_table_name)
        print(f"Initialized new target table: {target_table_name}")
        return

    delta_target = DeltaTable.forName(spark, target_table_name)

    # 2. Stage 1: Expire changed records (Match key, active status, but hash differs)
    join_key_cond = """
        target.TIME_SERIES_CODE = source.TIME_SERIES_CODE AND
        target.DATE = source.DATE AND
        target.IBS_AGG = source.IBS_AGG AND
        target.is_current = true
    """

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

    # 3. Stage 2: Insert new active records (New keys OR superseded versions)
    active_target = delta_target.toDF().filter("is_current = true")
    
    df_to_insert = df_source.alias("src").join(
        active_target.alias("tgt"),
        on=["TIME_SERIES_CODE", "DATE", "IBS_AGG"],
        how="left"
    ).filter(
        "tgt.TIME_SERIES_CODE IS NULL OR tgt.version_hash != src.version_hash"
    ).select("src.*") \
     .withColumn("effective_start_date", F.current_timestamp()) \
     .withColumn("effective_end_date", F.to_timestamp(F.lit("9999-12-31 00:00:00"))) \
     .withColumn("is_current", F.lit(True))

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
                target.is_current = true
            """
        ).whenMatchedUpdate(
            set={
                "is_current": "false",
                "effective_end_date": "current_timestamp()"
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