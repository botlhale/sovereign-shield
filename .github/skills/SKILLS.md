# 💻 Technical Skills & Architecture Competencies

## 🔐 Zero-Trust Cloud Security & Governance
* **Databricks Unity Catalog:** Architecting centralized, multi-layered data governance models across PySpark pipelines, SQL endpoints, and downstream BI tools.
* **Row-Level Security (RLS):** Developing dynamic SQL functions to enforce localized sovereign data access via composite key parsing and Entra ID group membership — applied to both aggregated and raw micro-transaction ledgers as defense in depth.
* **ANSI-Safe Policy Authoring:** Writing row filters that fail *closed* rather than *loud* (`try_element_at` over `element_at`), since an exception inside a row filter aborts every query against the table.
* **Dynamic Data Masking (DDM) / Column-Level Security:** Implementing conditional masking policies (`MASK ... USING COLUMNS`) that redact confidential metrics to a type-compatible `NULL` while preserving structural dimensional density for macroeconomic research.
* **Identity & Access Management (IAM):** Automating Service Principal (SPN) ownership binding via CI/CD, and reasoning about the distinction between object ownership and row-filter exemption.
* **Idempotent, Non-Destructive DDL Engineering:** Designing security scripts that re-execute on every pipeline run without erasing state — `CREATE TABLE IF NOT EXISTS` guards, detach → replace → re-attach sequencing for policy-bound functions, and explicit per-statement failure-tolerance markers with fail-fast defaults.
* **Security Regression Analysis:** Auditing data platforms for silent-failure classes — destructive DDL in an idempotent path, hash collisions between `NULL` and empty string, case-variant codes evading string-matched filters.

## ⚙️ Cloud Infrastructure & Orchestration
* **Databricks Asset Bundles (DABs):** Advanced configuration and deployment of CI/CD pipelines, managing infrastructure as code (IaC) in YAML, and optimizing workspace synchronization.
* **Compute Provisioning & Optimization:** Strategic Azure VM allocation and precise cluster topology configuration (Single Node vs. Driver-Worker setups).
* **Cluster Security Modes:** Deep expertise in Databricks execution models, explicitly configuring `USER_ISOLATION` (Shared) environments to natively enable and enforce Unity Catalog security constraints.
* **Runtime Path Resolution:** Handling Databricks `spark_python_task` execution contexts, where the entry script is run via `exec(compile(...))` and therefore has no `__file__` — recovering the true workspace path from the code object (`inspect.currentframe().f_code.co_filename`) through an ordered, lazily-evaluated candidate chain.

## 🛠️ Data Engineering & Distributed Processing
* **Apache Spark / PySpark:** High-performance distributed data processing, memory management, and pipeline orchestration.
* **Polars:** Blazing-fast DataFrame processing and optimization for localized and distributed analytical workloads.
* **Delta Lake Architecture:** Engineering robust Slowly Changing Dimensions (SCD Type 2) using `MERGE INTO` operations to securely historize data with valid-from/valid-to timestamps and active record flags — including scoped logical deletes, payload fingerprinting (`version_hash`), and anti-join replay idempotency.
* **Fail-Safe State Machines:** Designing merge semantics where a rejected submission is recorded as an audit-only record and the last known-good version stays active, so validation failure degrades to stale data rather than to missing data.
* **Micro-to-Macro Aggregations:** Designing engines that ingest, transform, and aggregate high-volume, multi-jurisdictional micro-transaction logs into standardized macro-level time series.
* **Local Spark-Free Prototyping:** Reproducing distributed merge semantics on pandas + `delta-rs` for environments without a JVM, and exercising Spark-path logic via `sys.modules` injection and mocking.

## 📊 Domain Expertise & Data Standards
* **SDMX 3.0 Framework:** Modernizing complex financial statistical ingestion frameworks to strictly comply with Statistical Data and Metadata eXchange formats, including SDMx 3.0 XML generation and DSD resolution via `pysdmx`.
* **Metadata-Driven Validation:** Building rule engines that compile official BIS consistency checks directly from the published `checks_lbs` workbook at runtime, rather than hard-coding business logic — including wildcard-dimension semantics and floating-point equality tolerances.
* **Atomic Batch Quarantine:** Implementing statistical-submission semantics where a country-quarter is accepted or rejected as an indivisible unit, since aggregate reconciliation is meaningless against partially-published components.
* **International Banking Statistics:** Engineering systems for cross-border financial data collection, validation, and multi-country sovereign data management, applying LBS conventions on signed positions, zero suppression, confidentiality escalation, and disclosure-control dominance thresholds computed on absolute contributions.
* **Time Series Modernization:** Architecting migration bridges (e.g., transforming legacy `uctl` frameworks to modern `pytimeseries` libraries) for advanced macroeconomic forecasting and statistical analysis.