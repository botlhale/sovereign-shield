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
* **Standards Layer:** `pysdmx` for SDMx 3.0 XML and DSD resolution; BIS consistency checks parsed at runtime from `docs/reference_standards/checks_lbs.xls`

## 📂 Project Structure

```text
.
├── databricks.yml                          # Asset Bundle configuration and deployment rules
├── requirements.txt                        # Task-scoped Python dependencies (pysdmx, xlrd, ...)
├── docs/
│   └── reference_standards/
│       └── checks_lbs.xls                  # BIS LBS consistency checks (parsed at runtime)
└── src/
    ├── apply_security.py                   # Idempotent Spark SQL executor for the Triple-Lock DDL
    ├── unity_catalog_triple_lock.sql       # DDL, RLS, DDM, and the Quarantine View
    ├── generate_sovereign_submissions.py   # Sovereign-isolated SDMx 3.0 XML submission generator
    ├── sdmx_rule_validator.py              # Dynamic BIS rule engine + atomic batch quarantine
    ├── scd2_merge_engine.py                # Micro-to-macro aggregation and Delta SCD2 state machine
    └── local_pandas_scd2.py                # Local pandas/delta-rs SCD2 prototype (no Spark required)

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

To enforce Unity Catalog's Row-Level Security (RLS) and Dynamic Data Masking (DDM) natively at the compute layer, the execution cluster is configured with `data_security_mode: USER_ISOLATION`. Single-user compute physically restricts RLS/DDM application to prevent unauthorized memory bypass.

* **Cost & Quota Optimization:** The pipeline runs a **Single Node** job cluster (`num_workers: 0`, `ResourceClass: SingleNode`, `spark.master: local[*, 4]`) on the `Standard_DS3_v2` family, and requests `SPOT_WITH_FALLBACK_AZURE` availability. This keeps the workload well inside Azure `DSv5` core quotas while retaining Unity Catalog enforcement.
* **Immutable Execution:** Scripts are executed via `spark_python_task`, which targets the synchronized `src/` workspace directory, stripping away the overhead and vulnerability of intermediate Python `.whl` compilation.

### 2. Dynamic Asset Execution in PySpark

A `spark_python_task` entry script is executed by Databricks via `exec(compile(source, filename, 'exec'))`. This creates two distinct hazards that must both be handled:

* `__file__` is **never bound**, so anchoring paths to it raises `NameError`.
* The working directory is **not** the bundle root, so `os.getcwd()` alone is equally unreliable.

Note that only the *entry script* is affected. Imported modules (such as `sdmx_rule_validator`) are loaded through the normal import machinery and do have `__file__`.

`apply_security.resolve_sql_path()` therefore walks an ordered list of candidates, exploiting the fact that the path handed to `compile()` survives inside the code object:

```python
module_file = globals().get("__file__")          # local runs and imports
frame = inspect.currentframe()                   # frame.f_code.co_filename == the real workspace path
sys.argv[0]                                      # some task launchers
os.path.join(os.getcwd(), "src"), os.getcwd()    # last-resort fallbacks
```

Resolution is deliberately **lazy** (inside a function, not at module import). Evaluated at import time, the failure would fire before `main()` could ever apply a fallback.

### 3. SDMx Observation Semantics

The pipeline honours two SDMx conventions that are easy to get wrong and that materially change validation behaviour:

* **Values are signed.** LBS positions are legitimately negative as well as positive. A negative observation is never, by itself, a validation failure.
* **Zeros are not reported.** A position that nets to exactly zero is dropped after aggregation rather than published as a `0` observation.

Because values are signed, the disclosure-control dominance rule is computed on **absolute** contributions (`|bank| / Σ|bank|`). A signed share would divide by zero on offsetting positions and could exceed `1`.

### 4. The Triple-Lock Zero-Trust Framework

Security is centralized at the Unity Catalog Metastore level. By abstracting governance away from the compute logic, RLS and DDM policies apply uniformly across PySpark pipelines, SQL endpoints, and downstream BI tools.

* **Target Catalog:** Relies on the pre-provisioned workspace catalog (`dbw_sovereignshield`) to eliminate the need for granting highly privileged Metastore Admin rights to the Service Principal.
* **Non-Destructive, Idempotent DDL:** `unity_catalog_triple_lock.sql` runs as the *first* task of *every* execution, so it must never drop the historical tables — doing so silently erases the entire SCD2 lineage. The script uses `CREATE TABLE IF NOT EXISTS` and a detach → replace → re-attach sequence, because Unity Catalog refuses to replace a function that is bound to a live row filter or column mask. Statements that legitimately fail on one lifecycle path (fresh create vs. re-apply) are annotated `-- @tolerate-failure` and skipped; every other failure aborts the deployment so the platform is never left partially secured.
* **Lock 1 — Row-Level Security (RLS):** Filters rows so national analysts only query their own sovereign data, matched via segment 9 of the 11-dimension SDMx key against Entra ID group membership. Uses `try_element_at` rather than `element_at`: under ANSI mode an out-of-range index raises `INVALID_ARRAY_INDEX` and would abort *every* query on the table, whereas `try_element_at` returns `NULL` and fails closed. A second filter, `fn_rls_micro_country_lock`, applies the same sovereign isolation to the raw `lbs_micro_transactions` ledger as defense in depth.
* **Lock 2 — Dynamic Data Masking (DDM):** Masks confidential (`C`) or non-publishable (`N`) `OBS_VALUE` metrics to `NULL` for unprivileged readers, preserving structural dimensional density so downstream joins never break. Privileged groups are evaluated first, so an authorized submitter always sees the true value.
* **Lock 3 — The Quarantine View:** A hardened abstraction layer (`v_lbs_sdmx_published`) exposing only rows that are both `BATCH_STATUS = 'PUBLISHED'` and `IS_CURRENT = true`.
* **Absolute SPN Ownership:** The deployment pipeline executes via CI/CD, so the Service Principal assumes ownership of all created tables, views, and functions, stripping direct governance from individual developers.

> **Deployment prerequisite:** the pipeline Service Principal **must** be a member of `sg-sovereignshield-admin`. The SCD2 engine reads the target table to locate records to expire; if the row filter hid those rows, the merge would treat every row as new — silently duplicating history and never closing prior versions.

### 5. Atomic Country-Quarter Batch Quarantine

BIS submissions are accepted or rejected as a whole, never partially. `SDMxRuleValidator` parses the consistency checks in `docs/reference_standards/checks_lbs.xls` at runtime and evaluates them against the aggregated batch, then applies the verdict atomically per `(reporting_country, date_scope)`:

| Outcome | `QUALITY_STATUS` | `BATCH_STATUS` | `FAILED_RULE_ID` |
| --- | --- | --- | --- |
| Any record in the batch fails | `FAIL` on **every** row | `QUARANTINE` | Every violated check code |
| All records pass | `PASS` | `PUBLISHED` | `NULL` |

The validator is the single source of truth for these three columns; no downstream stage overrides them.

### 6. SCD2 Revision Protection

The merge engine splits the incoming batch by `BATCH_STATUS` so that a rejected revision can never disturb live data:

* **Published revisions** follow the standard lifecycle — the prior record is closed (`IS_CURRENT = false`, `VALID_TO = transaction_timestamp`) and the new record is inserted with `IS_CURRENT = true` and `VALID_TO = 9999-12-31T00:00:00`.
* **Quarantined revisions** are appended as **audit-only** records with `IS_CURRENT = false` and `VALID_TO = VALID_FROM`. They are excluded from the expire-merge *and* from the scoped logical delete, so the previously published record **remains `IS_CURRENT = true`** and `v_lbs_sdmx_published` keeps serving the last valid state without interruption.

Re-running the pipeline is safe: an anti-join on key + `version_hash` prevents a replayed rejected submission from stacking duplicate audit rows.

To make this observable, `run_pipeline()` executes two submission cycles in order — a `baseline` in which every country reconciles and publishes, followed by a `revision` in which Canada re-reports figures that break two BIS cross-checks (`LBS_CC01` and `LBS_CC:04`).

## 📝 Bundle Configuration (`databricks.yml`)

The orchestration matrix that binds the Zero-Trust architecture. Task order matters: the security layer is provisioned **before** any data is written, so no table ever exists unprotected.

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
            # Step 1: Provision / refresh the Triple-Lock infrastructure
            - task_key: setup_triple_lock_schema
              job_cluster_key: sovereign_cluster
              spark_python_task:
                python_file: "src/apply_security.py"

            # Step 2: Generate the sovereign SDMx 3.0 submissions
            - task_key: generate_synthetic_data
              depends_on:
                - task_key: setup_triple_lock_schema
              job_cluster_key: sovereign_cluster
              spark_python_task:
                python_file: "src/generate_sovereign_submissions.py"
              libraries:
                - requirements: requirements.txt

            # Step 3: Micro-to-macro ingestion, validation, and SCD2 merge
            - task_key: run_scd2_merge
              depends_on:
                - task_key: generate_synthetic_data
              job_cluster_key: sovereign_cluster
              spark_python_task:
                python_file: "src/scd2_merge_engine.py"
              libraries:
                - requirements: requirements.txt

          job_clusters:
            - job_cluster_key: sovereign_cluster
              new_cluster:
                spark_version: "18.x-scala2.13"
                node_type_id: "Standard_DS3_v2"
                num_workers: 0 # STRICTLY NO WORKERS
                data_security_mode: USER_ISOLATION
                custom_tags:
                  ResourceClass: SingleNode
                spark_conf:
                  spark.databricks.cluster.profile: singleNode
                  spark.master: local[*, 4]
                azure_attributes:
                  availability: SPOT_WITH_FALLBACK_AZURE

```

---

## 🔑 Operational Prerequisites

1. **SPN group membership** — add `spn-sovereignshield-cicd` to `sg-sovereignshield-admin`, or the RLS filter will hide the target table from the merge engine.
2. **Credential hygiene** — the helper scripts under `sh/` are provisioning aids only. Never commit real secrets; source them from Key Vault or environment injection and keep `sh/` out of version control.