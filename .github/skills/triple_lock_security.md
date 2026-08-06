# Project SovereignShield: Zero-Trust Triple-Lock Security Architecture

## 🛡️ Overview

SovereignShield explores Zero-Trust for **SDMx 3.0 statistical submissions to an international body** (BIS Locational Banking Statistics). The perimeter being defended is a *national* boundary and a legal obligation, not a network segment — so "never trust, always verify" is resolved concretely: every consumer is re-authorised against Entra ID at query time, and entitlement is derived from the SDMx key itself. These are the same guarantees established SDMx implementations uphold in their application layers; here they are expressed one layer lower.

The pipeline enforces that model natively within **Databricks Unity Catalog**. By decoupling governance from compute logic, security policies are applied uniformly across PySpark pipelines, SQL endpoints, and downstream BI tools — there is no code path that can omit them, because they are not in the code path.

This document outlines the core architectural mandates, the DDL idempotency patterns, and the "Triple-Lock" framework used to secure International Banking Statistics (SDMx 3.0) data.

---

## 🏗️ Core Architectural Mandates

Deploying Row-Level Security (RLS) and Dynamic Data Masking (DDM) in Unity Catalog requires strict adherence to specific Databricks compute and execution parameters:

### 1. Shared Compute Isolation (`USER_ISOLATION`)

Unity Catalog physically restricts the application of RLS and DDM on `SINGLE_USER` clusters to prevent unauthorized memory bypass.

* **Mandate:** The deployment and execution clusters **must** be configured with `data_security_mode: USER_ISOLATION`.
* **Optimization:** The pipeline provisions a **Single Node** job cluster (`num_workers: 0`, `ResourceClass: SingleNode`, `spark.master: local[*, 4]`) on the `Standard_DS3_v2` family with `SPOT_WITH_FALLBACK_AZURE` availability, keeping the workload inside Azure `DSv5` core quotas.

### 1a. Service Principal Group Membership

The pipeline identity is subject to the same row filter as every other principal.

* **Mandate:** `spn-sovereignshield-cicd` **must** be a member of `sg-sovereignshield-admin`.
* **Failure mode:** The SCD2 engine reads the target table to locate records to expire. If the row filter hid those rows, the merge would observe an empty target, treat every incoming row as new, and silently duplicate history while never closing prior versions. This fails silently — there is no error, only corrupt lineage.

### 2. Pre-Provisioned Namespace Targeting

To eliminate the anti-pattern of granting Metastore Admin privileges to the CI/CD Service Principal, dynamic catalog creation (`CREATE CATALOG`) is strictly prohibited.

* **Mandate:** All assets are deployed into the pre-provisioned workspace catalog: `dbw_sovereignshield.sovereign_shield`.

### 3. Dynamic OS-Level Path Resolution

Databricks executes a `spark_python_task` entry script via `exec(compile(source, filename, 'exec'))`. This defeats **both** naive path strategies:

* `__file__` is never bound in the entry script → `NameError`.
* The working directory is not the bundle root → `os.getcwd()` alone is unreliable.

Only the entry script is affected; imported modules load normally and do have `__file__`.

* **Mandate:** Resolve across an ordered candidate list, and do it **lazily inside a function** — at module import time the failure fires before any fallback can run.

```python
# correct implementation for bundle path resolution
module_file = globals().get("__file__")          # local runs and imports
frame = inspect.currentframe()                   # frame.f_code.co_filename == the real workspace path
sys.argv[0]                                      # some task launchers
os.path.join(os.getcwd(), "src"), os.getcwd()    # last-resort fallbacks
```

The `compile()` filename survives inside the code object, which is what makes `frame.f_code.co_filename` the reliable recovery path under the Databricks wrapper.

---

## 🔒 The Triple-Lock Framework

The security architecture operates in three distinct layers, bound together by strict DDL idempotency requirements.

### Pre-Requisite: Non-Destructive, Idempotent DDL

`unity_catalog_triple_lock.sql` executes as the **first task of every pipeline run**, so its correctness constraints are unusually strict.

* **Never drop state.** The script contains no `DROP TABLE` or `DROP VIEW` statements. An earlier revision dropped `lbs_sdmx_history` on each run, which erased the entire SCD2 lineage every execution and presented as "all records show `IS_CURRENT = false`". Only `CREATE TABLE IF NOT EXISTS` and `CREATE OR REPLACE VIEW` are permitted.
* **Create before binding.** Unity Catalog requires target tables to physically exist before security policies bind to them; `ALTER TABLE ... SET ROW FILTER` on a missing table raises `TABLE_OR_VIEW_NOT_FOUND`.
* **Detach → replace → re-attach.** `CREATE OR REPLACE FUNCTION` fails while the function is bound to a live row filter or column mask. The script therefore drops the filters and masks first (§1), redefines the functions, recreates the tables, then re-attaches (§7).
* **Selective failure tolerance.** Statements that legitimately fail on one lifecycle path but not the other — detaching a filter on a table that does not yet exist, re-attaching one that is already bound — carry the marker below. The marker must be the *entire* comment on the preceding line; any other failure aborts the deployment rather than leaving the platform half-secured.

```sql
-- @tolerate-failure
ALTER TABLE lbs_sdmx_history DROP ROW FILTER;
```

The script currently parses to **29 statements, 6 of which are tolerated**.

### Lock 1: Row-Level Security (RLS)

Ensures strict national data sovereignty across **both** the macro history and the raw micro ledger.

* **Macro (`fn_rls_lbs_country_lock`):** Evaluates segment 9 of the 11-dimension SDMx `TIME_SERIES_CODE` and matches it against the executing user's Entra ID group membership (e.g. `sg-sovereignshield-submitter-ca`).
* **Micro (`fn_rls_micro_country_lock`):** Applies the same sovereign isolation directly to the `reporting_country` column of `lbs_micro_transactions`. Without this, the raw ledger would expose every jurisdiction's unaggregated transactions — the aggregate was protected while the source was not.
* **ANSI safety:** The macro filter uses `try_element_at(split(...), 9)`, **not** `element_at`. Under ANSI mode an out-of-range index raises `INVALID_ARRAY_INDEX`; because the filter runs on every row of every query, a single malformed key would abort *all* access to the table. `try_element_at` returns `NULL` instead, and the predicate fails closed.
* **Normalization:** Comparisons are performed on `upper(trim(...))` on both sides, so a lowercase country code cannot evade the filter.
* **Bypass:** System administrators (`sg-sovereignshield-admin`) inherently bypass this filter.

### Lock 2: Dynamic Data Masking (DDM)

Protects market dominance and strictly confidential reporting metrics while maintaining structural table integrity for researchers.

* **Mechanism:** `fn_ddm_obs_conf_mask(obs_val DOUBLE, obs_conf STRING)` is bound with `MASK ... USING COLUMNS (OBS_CONF)`. If a record is marked Non-publishable (`N`) or Confidential (`C`), the numerical `OBS_VALUE` is masked to `NULL`.
* **Why `NULL`, not `'xxx'`:** `OBS_VALUE` is a `DOUBLE`, and a masking function must return the column's own type. A string sentinel is not representable.
* **Privilege ordering:** Group membership is evaluated **before** the confidentiality branch, so an authorized admin or the owning submitter always sees the true value.
* **Benefit:** External researchers can still perform dimensional joins and assess reporting density without exposing restricted financial limits.

### Lock 3: The Quarantine View

Secures the "Quarterly Quarantine" by abstracting raw historical tables away from public researchers.

* **Mechanism:** Researchers are only granted `SELECT` access to a hardened view (`v_lbs_sdmx_published`).
* **Integrity Gate:** `WHERE BATCH_STATUS = 'PUBLISHED' AND IS_CURRENT = true`. Rejected batches are written as audit-only rows with `IS_CURRENT = false`, so they fail both predicates and remain invisible.

---

## 🤖 CI/CD Implicit Ownership (Zero-Trust IAM)

Previous iterations of this pipeline utilized explicit `ALTER OWNER TO spn-sovereignshield-cicd` statements. This has been deprecated in favor of Unity Catalog's native Identity and Access Management (IAM) behaviors.

* **The Zero-Trust Principle:** By strictly orchestrating all deployments through Azure DevOps/GitHub Actions via Databricks Asset Bundles, the executing **Service Principal implicitly and automatically assumes ownership** of all created schemas, tables, views, and functions.
* **Result:** Direct production governance and mutation capabilities are completely stripped from individual human developers.

---

## 📜 Appendix: Target DDL Schema Reference

Policies are attached inline at creation time so the table is never momentarily readable without governance. Note that `OBS_VALUE` may legitimately be negative — LBS positions record both asset and liability directions — while zero-valued observations are not reported at all under SDMx convention and are filtered upstream.

```sql
CREATE TABLE IF NOT EXISTS lbs_sdmx_history (
    TIME_SERIES_CODE STRING,      -- 11-dimension SDMx composite key
    DATE STRING,                  -- Observation period (e.g. '2026-Q1')
    IBS_AGG STRING,               -- Aggregation scope (e.g. 'LBSR')
    OBS_VALUE DOUBLE MASK fn_ddm_obs_conf_mask USING COLUMNS (OBS_CONF),
    OBS_STATUS STRING,
    OBS_CONF STRING,              -- 'F' | 'N' | 'C'
    QUALITY_STATUS STRING,        -- 'PASS' | 'FAIL' (validator verdict)
    FAILED_RULE_ID STRING,        -- Comma-joined BIS check codes, NULL when clean
    BATCH_STATUS STRING,          -- 'PUBLISHED' | 'QUARANTINE'
    version_hash STRING,          -- SCD2 payload fingerprint
    VALID_FROM TIMESTAMP,
    VALID_TO TIMESTAMP,
    IS_CURRENT BOOLEAN
)
WITH ROW FILTER fn_rls_lbs_country_lock ON (TIME_SERIES_CODE);

CREATE TABLE IF NOT EXISTS lbs_micro_transactions (
    transaction_id STRING,
    reporting_country STRING,
    reporting_institution STRING,
    position_type STRING,
    instrument STRING,
    currency STRING,
    currency_type STRING,
    parent_country STRING,
    bank_type STRING,
    counterpart_country STRING,
    sector_code STRING,
    transaction_amount DOUBLE,
    obs_conf STRING,
    ibs_agg_scope STRING,
    date_scope STRING,
    transaction_timestamp TIMESTAMP
)
WITH ROW FILTER fn_rls_micro_country_lock ON (reporting_country);

```