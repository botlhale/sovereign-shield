# Project SovereignShield: Zero-Trust Triple-Lock Security Architecture

## 🛡️ Overview

The SovereignShield pipeline enforces a cryptographic-grade, Zero-Trust security model natively within **Databricks Unity Catalog**. By decoupling governance from compute logic, security policies are uniformly applied across PySpark pipelines, SQL endpoints, and downstream BI tools.

This document outlines the core architectural mandates, the DDL idempotency patterns, and the "Triple-Lock" framework used to secure International Banking Statistics (SDMx 3.0) data.

---

## 🏗️ Core Architectural Mandates

Deploying Row-Level Security (RLS) and Dynamic Data Masking (DDM) in Unity Catalog requires strict adherence to specific Databricks compute and execution parameters:

### 1. Shared Compute Isolation (`USER_ISOLATION`)

Unity Catalog physically restricts the application of RLS and DDM on `SINGLE_USER` clusters to prevent unauthorized memory bypass.

* **Mandate:** The deployment and execution clusters **must** be configured with `data_security_mode: USER_ISOLATION`.
* **Optimization:** To bypass Azure `DSv5` quota limits while meeting the multi-node requirement of Shared clusters, the CI/CD pipeline allocates the `Standard_DS3_v2` VM family with exactly **1 worker node**.

### 2. Pre-Provisioned Namespace Targeting

To eliminate the anti-pattern of granting Metastore Admin privileges to the CI/CD Service Principal, dynamic catalog creation (`CREATE CATALOG`) is strictly prohibited.

* **Mandate:** All assets are deployed into the pre-provisioned workspace catalog: `dbw_sovereignshield.sovereign_shield`.

### 3. Dynamic OS-Level Path Resolution

Databricks interactive execution environments (used by `spark_python_task`) do not support the native Python `__file__` attribute.

* **Mandate:** Python wrappers executing SQL assets must use `os.getcwd()` to dynamically resolve paths within the deployed Databricks Asset Bundle (DAB).

```python
# correct implementation for bundle path resolution
import os
cwd = os.getcwd()
sql_path = os.path.join(cwd, "src", "unity_catalog_triple_lock.sql")

```

---

## 🔒 The Triple-Lock Framework

The security architecture operates in three distinct layers, bound together by strict DDL idempotency requirements.

### Pre-Requisite: DDL Idempotency Guards

Unity Catalog requires target tables to physically exist in the metastore *before* security policies can be bound to them. Attempting to run `ALTER TABLE ... SET ROW FILTER` on a non-existent table will result in a `TABLE_OR_VIEW_NOT_FOUND` exception.

* **Implementation:** The SQL architecture script proactively invokes `CREATE TABLE IF NOT EXISTS` for both the micro-transaction and macro-history tables before defining any functions or views.

### Lock 1: Row-Level Security (RLS)

Ensures strict national data sovereignty. Analysts can only query macro-level data belonging to their respective reporting jurisdictions.

* **Mechanism:** A dynamic SQL function evaluates the 9th index (index 8) of the 11-dimension SDMx `TIME_SERIES_CODE` and matches it against the executing user's Entra ID group membership (e.g., `sg-sovereignshield-submitter-ca`).
* **Bypass:** System administrators (`sg-sovereignshield-admin`) inherently bypass this filter.

### Lock 2: Dynamic Data Masking (DDM)

Protects market dominance and strictly confidential reporting metrics while maintaining structural table integrity for researchers.

* **Mechanism:** Evaluates the `OBS_CONF` (Observation Confidentiality) flag. If a record is marked as Non-publishable (`N`) or Confidential (`C`), the numerical `OBS_VALUE` is dynamically masked to `'xxx'`.
* **Benefit:** External researchers can still perform dimensional joins and assess reporting volume density without exposing restricted financial limits.

### Lock 3: The Quarantine View

Secures the "Quarterly Quarantine" by abstracting raw historical tables away from public researchers.

* **Mechanism:** Researchers are only granted `SELECT` access to a hardened view (`v_lbs_sdmx_published`).
* **Integrity Gate:** The view explicitly filters out incomplete or under-review batches (`WHERE BATCH_STATUS = 'PUBLISHED'`) and ensures only active Slowly Changing Dimension records are exposed (`IS_CURRENT = true`).

---

## 🤖 CI/CD Implicit Ownership (Zero-Trust IAM)

Previous iterations of this pipeline utilized explicit `ALTER OWNER TO spn-sovereignshield-cicd` statements. This has been deprecated in favor of Unity Catalog's native Identity and Access Management (IAM) behaviors.

* **The Zero-Trust Principle:** By strictly orchestrating all deployments through Azure DevOps/GitHub Actions via Databricks Asset Bundles, the executing **Service Principal implicitly and automatically assumes ownership** of all created schemas, tables, views, and functions.
* **Result:** Direct production governance and mutation capabilities are completely stripped from individual human developers.

---

## 📜 Appendix: Target DDL Schema Reference

For RLS, DDM, and Quarantine views to successfully bind, the target historical table must be initialized with the complete analytical schema:

```sql
CREATE TABLE IF NOT EXISTS lbs_sdmx_history (
    TIME_SERIES_CODE STRING,      
    DATE STRING,                  
    IBS_AGG STRING,               
    OBS_VALUE DOUBLE,
    OBS_STATUS STRING,            
    OBS_CONF STRING,
    BATCH_STATUS STRING,          
    VALID_FROM TIMESTAMP,
    VALID_TO TIMESTAMP,
    IS_CURRENT BOOLEAN
) USING DELTA;

```