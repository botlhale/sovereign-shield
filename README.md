# Project SovereignShield: Zero-Trust SDMx 3.0 Governance

## 📖 Executive Summary

Project SovereignShield represents a paradigm shift in the governance, ingestion, and validation of International Banking Statistics. Moving beyond legacy infrastructure, this architecture establishes a heavily fortified, **Zero-Trust data pipeline** designed to strictly enforce the **SDMx 3.0 standard**.

At its core, SovereignShield ensures absolute data sovereignty. As micro-level financial transactions from diverse reporting jurisdictions are ingested and aggregated into macro-level SDMx dimensions, the system applies uncompromising, cryptographic-grade governance. By leveraging Azure Databricks and Unity Catalog, the framework guarantees that national statistical boundaries are respected, confidential data is dynamically masked from unauthorized researchers, and human intervention in production environments is systematically eliminated.

---

## 🏗️ Modernized Architecture Stack

* **Compute Engine:** Azure Databricks (Runtime 18.x LTS)
* **Storage:** Delta Lake (SCD2 Historization)
* **Central Governance:** Unity Catalog (`USER_ISOLATION` Shared Compute)
* **Orchestration:** Databricks Asset Bundles (CI/CD via Azure Service Principal)
* **Processing Framework:** PySpark & Spark SQL

## 📂 Project Structure

```text
.
├── databricks.yml                      # Asset Bundle configuration and deployment rules
└── src/
    ├── scd2_merge_engine.py            # Micro-data simulation, SDMx aggregation, and Delta SCD2 logic
    ├── apply_security.py               # Dynamic Spark SQL execution wrapper for workspace files
    └── unity_catalog_triple_lock.sql   # DDL definitions, RLS, DDM, and Quarantine Views

```

## 🚀 Deployment & Execution

SovereignShield enforces Zero-Trust by requiring all deployments and pipeline executions to be orchestrated natively via Databricks Asset Bundles using a designated CI/CD Service Principal.

**1. Sync to Azure Databricks Workspace:**

```bash
databricks bundle deploy -t dev

```

*(Note: To ensure the entire `src/` directory syncs seamlessly and respects the repository structure, `databricks.yml` intentionally omits explicit `.yml` `include:` blocks).*

**2. Trigger the Pipeline:**

```bash
databricks bundle run sovereignshield_sdmx_pipeline -t dev

```

## 🛡️ Core Technical Implementations & Zero-Trust Design Patterns

### 1. Unity Catalog Governance & Compute Isolation

To enforce Unity Catalog's Row-Level Security (RLS) and Dynamic Data Masking (DDM) natively at the compute layer, the execution cluster **must** be configured as a Shared cluster (`USER_ISOLATION`). Single-user compute physically restricts RLS/DDM application to prevent unauthorized memory bypass.

* **Core Quota Bypass:** To satisfy the Shared cluster node requirement (Driver + Worker) without breaching Azure `DSv5` family quota limits, the pipeline utilizes the `Standard_DS3_v2` VM family locked to exactly `1` worker (8 cores total).
* **Immutable Execution:** Scripts are executed via `spark_python_task`, which automatically targets the synchronized `src/` workspace directory, stripping away the overhead and vulnerability of intermediate Python `.whl` compilation.

### 2. Dynamic Asset Execution in PySpark

Databricks interactive execution environments do not natively support the Python `__file__` variable. To dynamically locate and execute the SQL security architecture scripts synced via the CLI, the path is robustly constructed using `os.getcwd()`, binding the execution exclusively to the bundle's isolated root directory:

```python
import os
cwd = os.getcwd()
sql_path = os.path.join(cwd, "src", "unity_catalog_triple_lock.sql")

```

### 3. The Triple-Lock Zero-Trust Framework

Security is centralized at the Unity Catalog Metastore level. By abstracting governance away from the compute logic, RLS and DDM policies apply uniformly across PySpark pipelines, SQL endpoints, and downstream BI tools.

* **Target Catalog:** Relies on the pre-provisioned workspace catalog (`dbw_sovereignshield`) to eliminate the need for granting highly privileged Metastore Admin rights to the Service Principal.
* **Idempotent DDL Guards:** Unity Catalog strictly requires target tables to exist *before* security policies are attached. `CREATE TABLE IF NOT EXISTS` is proactively invoked prior to any `ALTER TABLE` statements to guarantee pipeline idempotency.
* **Lock 1: Row-Level Security (RLS):** Dynamically filters rows so national analysts can only query their specific sovereign data (matched via the 9th index of the SDMx composite key mapped against their Entra ID group membership).
* **Lock 2: Dynamic Data Masking (DDM):** Preserves structural dimensional density for broad macroeconomic research by masking confidential (`C`) or non-publishable (`N`) `OBS_VALUE` metrics to `'xxx'`, ensuring downstream joins never break.
* **Lock 3: The Quarantine View:** A hardened abstraction layer (`v_lbs_sdmx_published`) ensuring external researchers can exclusively query data explicitly marked as `PUBLISHED` and actively current (`IS_CURRENT = true`).
* **Absolute SPN Ownership:** Because the deployment pipeline executes via CI/CD, the Service Principal inherently assumes complete ownership of all created tables, views, and functions. This successfully strips direct governance and mutation capabilities from individual human developers.

## 📝 Bundle Configuration (`databricks.yml`)

The orchestration matrix that binds the Zero-Trust architecture:

```yaml
bundle:
  name: sovereignshield_bundle

targets:
  dev:
    default: true
    mode: development
    workspace:
      host: https://adb-<workspace-id>.xx.azuredatabricks.net
    
    resources:
      jobs:
        sovereignshield_sdmx_pipeline:
          name: "[DEV] SovereignShield SDMx Ingestion & Validation"
          tasks:
            - task_key: run_scd2_merge
              job_cluster_key: sovereign_cluster
              spark_python_task:
                python_file: "src/scd2_merge_engine.py"
            
            - task_key: execute_triple_lock_security
              depends_on:
                - task_key: run_scd2_merge
              job_cluster_key: sovereign_cluster
              spark_python_task:
                python_file: "src/apply_security.py"

          job_clusters:
            - job_cluster_key: sovereign_cluster
              new_cluster:
                spark_version: "18.x-scala2.13"
                node_type_id: "Standard_DS3_v2"
                num_workers: 1
                data_security_mode: USER_ISOLATION

```