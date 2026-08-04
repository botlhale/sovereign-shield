# Project SovereignShield: SDMx Slowly Changing Dimension (SCD2) Engine

## 🔄 Overview

The SCD2 Merge Engine is the data processing core of Project SovereignShield. It is responsible for bridging the gap between raw, multi-jurisdictional micro-transactions and the centralized **SDMx 3.0** macro-historical tables.

This engine operates in a strict two-step flow: it first ingests and aggregates granular financial records into standard SDMx dimensions, and then securely historizes those aggregations into Delta Lake using a Slowly Changing Dimension Type 2 (SCD2) architecture.

---

## ⚙️ Compute & Infrastructure Strategy

To fully support Unity Catalog's Zero-Trust governance model while navigating Azure infrastructure constraints, the underlying compute engine for this pipeline is meticulously configured:

* **Runtime:** Databricks Runtime **18.x LTS** (`18.x-scala2.13`) to leverage the latest PySpark optimizations, Delta Lake features, and Unity Catalog integrations.
* **Quota Optimization (The DSv5 Bypass):** Unity Catalog's Row-Level Security (RLS) requires a `USER_ISOLATION` (Shared) cluster, which mandates a multi-node setup (Driver + Worker). To avoid Azure `DSv5` core quota exceptions, the engine provisions the **`Standard_DS3_v2`** VM family locked to exactly **1 worker node** (8 cores total). This satisfies the Unity Catalog requirement without breaching subscription limits.

---

## 🌊 Phase 1: Micro-to-Macro Aggregation

Before any historical merging occurs, the engine must process incoming micro-data submitted by various reporting countries (e.g., Canada, USA, UK).

### 1. Ingestion of Micro-Transactions

The pipeline captures granular transaction logs (`lbs_micro_transactions`) detailing counterparty countries, sector codes, transaction amounts, and individual observation confidentiality flags (`OBS_CONF`).

### 2. SDMx 3.0 Dimensional Rollup

Using PySpark, the micro-data is grouped by analytical dimensions (e.g., `reporting_country`, `ibs_agg_scope`, `currency`, `date_scope`) and rolled up into the standard SDMx format.

* **Metric Aggregation:** Transaction amounts are summed to create the macro `OBS_VALUE`.
* **Confidentiality Elevation:** The engine dynamically evaluates the `OBS_CONF` array within the grouped records. If *any* underlying transaction in the rollup is flagged as Confidential (`C`), the entire macro aggregation is elevated to `C`. If there are no `C` flags but an `N` (Non-publishable) exists, it elevates to `N`. Otherwise, it remains `F` (Free for publication).
* **Composite Key Generation:** Constructs the 11-dimension SDMx `TIME_SERIES_CODE` (e.g., `BIS.LBS.S.A.<SCOPE>.<CURRENCY>.<COUNTRY>`).

---

## 🕰️ Phase 2: The SCD2 Delta Merge

Once the micro-data is aggregated into a macro DataFrame, it is passed into the SCD2 Delta `MERGE INTO` operation. This step compares the incoming data against the pre-existing `dbw_sovereignshield.sovereign_shield.lbs_sdmx_history` table.

The engine executes three simultaneous operations to maintain a perfect audit trail of all data mutations:

1. **Insert New Records:** If an incoming `TIME_SERIES_CODE` does not exist in the history table, it is inserted with `IS_CURRENT = true`, `VALID_FROM = current_timestamp`, and `VALID_TO = null`.
2. **Expire Changed Records:** If an incoming `TIME_SERIES_CODE` matches an existing active record (`IS_CURRENT = true`) but the `OBS_VALUE` or `OBS_CONF` has changed, the engine "expires" the old record by updating `IS_CURRENT = false` and setting `VALID_TO = current_timestamp`.
3. **Insert Updated Active Records:** For the records that were just expired in step 2, the engine inserts the newly calculated values as a brand new row with `IS_CURRENT = true`.

---

## 📜 Code Execution Flow (`src/scd2_merge_engine.py`)

The pipeline explicitly separates the aggregation logic from the Delta merge logic to ensure the code remains modular and easily testable.

```python
if __name__ == "__main__":
    spark = SparkSession.builder.getOrCreate()
    
    # Step 1: Ingest and aggregate multi-country micro-transactions
    print("Generating and aggregating micro data...")
    sdmx_updates_df = generate_and_aggregate_micro_data(spark)
    
    # Step 2: Push aggregated macro data through the SCD2 Delta Merge
    print("Executing SCD2 merge into historical table...")
    perform_scd2_merge(spark, sdmx_updates_df)
    
    print("Pipeline execution complete!")

```

By enforcing this two-step architecture, Project SovereignShield guarantees that downstream researchers only ever interact with structurally validated, securely historized, and fully aggregated macro dimensions.