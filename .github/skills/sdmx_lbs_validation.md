# Project SovereignShield: SDMx 3.0 Data Validation & Schema Enforcement

## 📊 Overview

As Project SovereignShield transitions the International Banking Statistics framework from legacy infrastructure to the **SDMx 3.0 standard**, strict data validation becomes paramount.

The validation layer acts as the primary gatekeeper. It ensures that raw micro-transactions are correctly aggregated, structurally aligned with the target schema, and dimensionally accurate *before* they are committed to the Delta Lake Slowly Changing Dimension (SCD2) history tables.

---

## 🏗️ Target Schema Alignment

During the macro-aggregation phase, the pipeline must strictly conform to the unified analytical schema. This schema was intentionally expanded to support both Zero-Trust security views and complex macroeconomic research.

The incoming DataFrame must be validated against the following structure before initiating the Delta `MERGE INTO` operation:

```sql
CREATE TABLE IF NOT EXISTS lbs_sdmx_history (
    TIME_SERIES_CODE STRING,      -- 11-dimension SDMx composite key
    DATE STRING,                  -- Standardized observation period (e.g., '2026-Q1')
    IBS_AGG STRING,               -- Aggregation scope (e.g., 'LBSR')
    OBS_VALUE DOUBLE,             -- The aggregated numeric metric
    OBS_STATUS STRING,            -- Observation status flag
    OBS_CONF STRING,              -- Confidentiality flag ('F', 'N', 'C')
    BATCH_STATUS STRING,          -- Processing state (e.g., 'QUARANTINE', 'PUBLISHED')
    VALID_FROM TIMESTAMP,         -- SCD2 Start Time
    VALID_TO TIMESTAMP,           -- SCD2 End Time
    IS_CURRENT BOOLEAN            -- SCD2 Active Record Flag
) USING DELTA;

```

---

## 🛡️ Pre-SCD2 Validation Rules

To prevent schema corruption and ensure downstream Row-Level Security (RLS) policies function correctly, the PySpark engine executes critical validation rules against the aggregated DataFrame immediately prior to historization.

### 1. Composite Key & Jurisdiction Validation

The `TIME_SERIES_CODE` is an 11-dimension string separated by dots (e.g., `BIS.LBS.S.A.<SCOPE>.<CURRENCY>.<COUNTRY>`).

* **The Rule:** The validation engine parses this string, splits it into an array, and isolates the 9th dimension (Index 8 in Spark SQL), which represents the reporting jurisdiction (e.g., `ca`, `us`).
* **The Enforcement:** The engine asserts that the derived country code in the `TIME_SERIES_CODE` perfectly matches the source `reporting_country` attribute from the micro-data batch. This prevents sovereign data cross-contamination and ensures the Unity Catalog RLS policy (`fn_rls_country_access`) evaluates the correct jurisdiction.

### 2. Confidentiality Flag Elevation

Micro-transactions carry individual confidentiality tags. The macro-level `OBS_CONF` flag must reflect the most restrictive tag of its underlying components.

* **The Rule:** If any single micro-transaction within a dimensional group is flagged as Confidential (`C`), the aggregated macro record must be forced to `C`. If no `C` exists but a Non-publishable (`N`) record is present, the macro record becomes `N`.
* **The Enforcement:** This guarantees that the Unity Catalog Dynamic Data Masking (DDM) policy (`fn_ddm_confidential_value`) correctly identifies and masks protected numeric values to `'xxx'` for external researchers.

---

## 🚧 The Quarantine Gate (`BATCH_STATUS`)

A critical component of the validation lifecycle is the `BATCH_STATUS` lifecycle.

1. **Ingestion:** When macro-records are first merged into `dbw_sovereignshield.sovereign_shield.lbs_sdmx_history`, they are typically ingested with a `BATCH_STATUS` of `QUARANTINE` or `UNDER_REVIEW`.
2. **Review:** Internal statistical analysts review the structural integrity and dimensional density of the quarantined data.
3. **Publication:** Once manually or programmatically approved, the `BATCH_STATUS` is updated to `PUBLISHED`.

**The Security Bind:** The public-facing researcher view (`v_lbs_sdmx_published`) hardcodes a filter `WHERE BATCH_STATUS = 'PUBLISHED'`. This guarantees that unvalidated, incomplete, or rejected SDMx aggregations never inadvertently leak into public macroeconomic datasets.