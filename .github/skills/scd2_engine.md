# Project SovereignShield: SDMx Slowly Changing Dimension (SCD2) Engine

## 🔄 Overview

The SCD2 Merge Engine is the data processing core of Project SovereignShield. It is responsible for bridging the gap between raw, multi-jurisdictional micro-transactions and the centralized **SDMx 3.0** macro-historical tables.

This engine operates in a strict two-step flow: it first ingests and aggregates granular financial records into standard SDMx dimensions, and then securely historizes those aggregations into Delta Lake using a Slowly Changing Dimension Type 2 (SCD2) architecture.

---

## ⚙️ Compute & Infrastructure Strategy

To fully support Unity Catalog's Zero-Trust governance model while navigating Azure infrastructure constraints, the underlying compute engine for this pipeline is meticulously configured:

* **Runtime:** Databricks Runtime **18.x LTS** (`18.x-scala2.13`) to leverage the latest PySpark optimizations, Delta Lake features, and Unity Catalog integrations.
* **Cost & Quota Optimization:** Unity Catalog's Row-Level Security requires a `USER_ISOLATION` cluster. The engine runs this on a **Single Node** job cluster (`num_workers: 0`, `ResourceClass: SingleNode`, `spark.master: local[*, 4]`) using the `Standard_DS3_v2` family with `SPOT_WITH_FALLBACK_AZURE` availability — satisfying the Unity Catalog requirement without breaching `DSv5` core quotas.
* **Identity:** The executing Service Principal **must** belong to `sg-sovereignshield-admin`. The merge reads the target table to find records to expire; if RLS hid those rows the engine would treat every incoming row as new and silently duplicate history.
* **Local development:** the pipeline cannot run locally without a JVM. Use `src/local_pandas_scd2.py`, which reproduces the identical SCD2 state machine on pandas + delta-rs.

---

## 🌊 Phase 1: Micro-to-Macro Aggregation

Before any historical merging occurs, the engine must process incoming micro-data submitted by various reporting countries (e.g., Canada, USA, UK).

### 1. Ingestion of Micro-Transactions

The pipeline captures granular transaction logs (`lbs_micro_transactions`) detailing counterparty countries, sector codes, transaction amounts, and individual observation confidentiality flags (`OBS_CONF`).

### 2. SDMx 3.0 Dimensional Rollup

Using PySpark, the micro-data is grouped by the analytical dimensions and rolled up into the standard SDMx format.

* **Normalization First:** Every code column is rewritten with `upper(trim(...))` *before* grouping. Case variants would otherwise split a single series into two groups and — more seriously — allow a lowercase country code to evade the RLS filter downstream.
* **Codelist Enforcement:** `_assert_valid_sector_codes` fails the batch if any `sector_code` falls outside the BIS codelist (`B`, `M`, `F`, `C`, `G`, `H` breakdowns plus `A`, `N`, `U` aggregates). Placeholder values are rejected rather than silently aggregated.
* **Metric Aggregation:** Transaction amounts are summed to create the macro `OBS_VALUE`.
* **Confidentiality Elevation:** If *any* underlying transaction in the rollup is flagged Confidential (`C`), the macro aggregation is elevated to `C`. If no `C` exists but an `N` (Non-publishable) does, it elevates to `N`. Otherwise it remains `F`.
* **Composite Key Generation:** Constructs the 11-dimension SDMx `TIME_SERIES_CODE` by `concat_ws(".", ...)` in fixed dimensional order:

  ```text
  FREQ . L_MEASURE . L_POSITION . L_INSTR . L_DENOM . L_CURR_TYPE
       . L_PARENT_CTY . L_REP_BANK_TYPE . L_REP_CTY . L_CP_SECTOR . L_CP_COUNTRY

  e.g.  Q.S.C.B.CAD.D.CA.A.CA.B.5J
  ```

  Segment **9** is the reporting jurisdiction — the exact segment the RLS filter parses.
* **Zero Suppression:** A final `filter(OBS_VALUE IS NOT NULL AND OBS_VALUE != 0)` is applied. Under SDMx convention a position netting to exactly zero is not reported at all. Negative values, by contrast, are entirely valid and are retained.

### 3. Batch Stamping

All three batch columns (`ibs_agg_scope`, `date_scope`, `transaction_timestamp`) are appended to the row literals programmatically, using a **single** UTC timestamp captured once per batch. Stamping `datetime.now()` per row would make rows within one submission non-comparable and defeat idempotency checks. A width guard rejects any row literal that does not match the expected arity, converting what would otherwise surface as an opaque `AXIS_LENGTH_MISMATCH` into an error naming the offending `transaction_id`.

---

## 🕰️ Phase 2: Validation Gate & The SCD2 Delta Merge

Between aggregation and historization sits the validation gate. `SDMxRuleValidator` evaluates the BIS consistency checks and assigns `QUALITY_STATUS`, `BATCH_STATUS`, and `FAILED_RULE_ID` **atomically per `(reporting_country, date_scope)`**: if any record in a country-quarter fails, every record in that batch is marked `FAIL` / `QUARANTINE`. The validator is the sole author of these three columns; the merge engine never overrides them.

The merge then splits the incoming DataFrame on `BATCH_STATUS` and runs four stages against `dbw_sovereignshield.sovereign_shield.lbs_sdmx_history`.

### Stage 1 — Expire Changed Records (published only)

Merged on the natural key (`TIME_SERIES_CODE`, `DATE`, `IBS_AGG`), matching only where `target.version_hash != source.version_hash`. The prior record is closed with `IS_CURRENT = false` and `VALID_TO = current_timestamp()`.

The `version_hash` is a fingerprint over the payload columns. Each component is coalesced against a `\u0000NULL` sentinel rather than an empty string — with `""`, a genuine NULL and an empty value would hash identically and a real revision could be missed.

### Stage 2 — Insert New Active Records (published only)

New and revised published rows are inserted with `IS_CURRENT = true`, `VALID_FROM = current_timestamp()`, and `VALID_TO = 9999-12-31T00:00:00` (an explicit end-of-time sentinel, not `NULL`, so range predicates need no special-casing).

### Stage 2b — Quarantine Audit Append

Rejected rows are appended as **audit-only** records: `IS_CURRENT = false` and `VALID_TO = VALID_FROM`. They are deliberately excluded from Stage 1, so the previously published record **remains active**. A rejected revision is recorded for lineage but never disturbs what researchers can see.

Idempotency is enforced with a `left_anti` join on key + `version_hash`, so replaying a rejected submission does not stack duplicate audit rows.

### Stage 3 — Scoped Logical Delete

Series that existed previously but are absent from the current submission are closed out. Two constraints apply:

* The target is **re-read** after Stages 2/2b rather than reusing the pre-insert snapshot, which would otherwise immediately expire the rows just inserted.
* The scope is restricted to the `(reporting_country, DATE)` pairs actually present in the *published* portion of the batch. Without this, submitting Canada's quarter would logically delete every other jurisdiction's series.

---

## 🛡️ SCD2 State Guarantees

| Incoming `BATCH_STATUS` | Prior active record | New record written | Visible in `v_lbs_sdmx_published` |
| --- | --- | --- | --- |
| `PUBLISHED` (changed) | Expired (`IS_CURRENT = false`) | `IS_CURRENT = true` | Yes — the new value |
| `PUBLISHED` (unchanged) | Untouched | None | Yes — unchanged |
| `QUARANTINE` | **Untouched, stays active** | Audit row, `IS_CURRENT = false` | Yes — the *last valid* value |

Re-running the pipeline end-to-end is safe: row counts and active-record counts remain stable across replays.

---

## 📜 Code Execution Flow (`src/scd2_merge_engine.py`)

`run_pipeline` drives two submission cycles so the quarantine behaviour is directly observable: a `baseline` in which every jurisdiction reconciles and publishes, followed by a `revision` in which Canada re-reports figures that break two BIS cross-checks.

```python
if __name__ == "__main__":
    spark = SparkSession.builder.getOrCreate()
    run_pipeline(spark)


def run_pipeline(spark, date_scope="2026-Q1", ibs_agg_scope="LBSR"):
    for cycle in ("baseline", "revision"):
        process_and_publish_macro_batch(
            spark, date_scope=date_scope, ibs_agg_scope=ibs_agg_scope, cycle=cycle
        )


def process_and_publish_macro_batch(spark, date_scope, ibs_agg_scope, cycle):
    df_macro = generate_and_aggregate_micro_data(spark, date_scope, cycle, ibs_agg_scope)
    df_validated = validate(df_macro.toPandas())      # assigns BATCH_STATUS atomically
    merge_scd2_macro(spark, spark.createDataFrame(df_validated, VALIDATED_MACRO_SCHEMA))

```

By enforcing this architecture, Project SovereignShield guarantees that downstream researchers only ever interact with structurally validated, securely historized, and fully aggregated macro dimensions — and that a failed submission degrades gracefully to the last known-good state rather than to nothing at all.