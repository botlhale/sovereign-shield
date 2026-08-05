# Project SovereignShield: Persona & Role-Based Access Control (RBAC) Matrix

## 🔐 Overview

Project SovereignShield implements a Zero-Trust, Role-Based Access Control (RBAC) model driven natively by **Databricks Unity Catalog** and synchronized with Azure Entra ID.

By centralizing governance at the metastore level, this matrix guarantees that data sovereignty, confidentiality limits, and quarantine lifecycles are cryptographically enforced across all compute environments, regardless of how a user accesses the data (e.g., Databricks SQL, PySpark, or Power BI).

---

## 🎯 Target Namespace

All governance policies and access grants in this matrix apply strictly to the pre-provisioned workspace catalog environment:
**`dbw_sovereignshield.sovereign_shield`**

---

## 🎭 Persona Definitions & Access Profiles

### 1. The Execution Identity (CI/CD Service Principal)

* **Entra ID / SPN:** `spn-sovereignshield-cicd`
* **Role:** Automated Pipeline Orchestrator & Asset Owner.
* **Access Level:** Implicit Owner. By executing the Databricks Asset Bundles (DABs), this principal automatically assumes complete ownership of all created tables, views, schemas, and security functions.
* **Mandatory Group Membership:** the SPN **must** also be a member of `sg-sovereignshield-admin`. Ownership alone does not exempt a principal from a row filter. The SCD2 engine reads the target table to locate the records it must expire; if RLS hid those rows, the merge would see an empty target, treat every incoming row as new, and silently duplicate history without ever closing prior versions. This failure is silent — no exception is raised, only the lineage is corrupted.
* **Security Bind:** No individual human developer holds mutation or DDL execution rights in production. All structural changes must pass through version control and be deployed by this identity.

### 2. System Administrators

* **Entra ID Group:** `sg-sovereignshield-admin`
* **Role:** Internal data platform administrators and principal data engineers troubleshooting the pipeline.
* **Access Level:** Full Read Access to the raw historical table (`lbs_sdmx_history`) and the raw micro ledger (`lbs_micro_transactions`).
* **Security Bind:** Explicitly bypasses all Row-Level Security (RLS) filters and Dynamic Data Masking (DDM) policies. Can view all sovereign data and all unmasked `OBS_VALUE` metrics globally, including `QUARANTINE` batches.

### 3. National Analysts / Submitters

* **Entra ID Group:** `sg-sovereignshield-submitter-<country_code>` (e.g., `sg-sovereignshield-submitter-ca`)
* **Role:** Regional data stewards responsible for validating and analyzing their specific jurisdiction's SDMx submissions.
* **Access Level:** Restricted Read Access to **both** the macro history (`lbs_sdmx_history`) and the raw micro ledger (`lbs_micro_transactions`).
* **Security Bind (RLS — macro):** `fn_rls_lbs_country_lock` parses segment 9 of the `TIME_SERIES_CODE` and matches it to the user's group suffix. Comparison is case-normalized, and an out-of-range index resolves to `NULL` via `try_element_at` — failing closed rather than aborting the query.
* **Security Bind (RLS — micro):** `fn_rls_micro_country_lock` applies the identical restriction to the `reporting_country` column. Without it, the aggregate would be protected while the unaggregated source remained fully exposed.
* **Security Bind (DDM):** Bypasses Dynamic Data Masking for their own sovereign data. They can see raw `OBS_VALUE` numbers even if the record is flagged as Confidential (`C`) or Non-publishable (`N`).
* **Quarantine Visibility:** Submitters see their own `QUARANTINE` batches together with the `FAILED_RULE_ID` codes, which is what makes a rejected submission diagnosable.

### 4. External Researchers

* **Entra ID Group:** `sg-sovereignshield-researchers`
* **Role:** Macroeconomic researchers, cross-regional analysts, and public data consumers.
* **Access Level:** Highly Restricted View Access. They are denied direct access to `lbs_sdmx_history` and `lbs_micro_transactions`, and must query the abstraction layer: `v_lbs_sdmx_published`.
* **Security Bind (The Quarantine Gate):** The view filters for `BATCH_STATUS = 'PUBLISHED' AND IS_CURRENT = true`. Rejected batches are persisted as audit-only rows (`IS_CURRENT = false`, `VALID_TO = VALID_FROM`) and therefore fail both predicates. Critically, a rejected revision does **not** expire the prior published record — researchers continue to see the last valid state rather than a gap.
* **Security Bind (DDM):** Fully bound by Dynamic Data Masking. If `OBS_CONF` is `C` or `N`, the `OBS_VALUE` is masked to `NULL` (the masking function must return the column's own `DOUBLE` type, so a string sentinel such as `'xxx'` is not representable). This preserves structural dimensional density — complex SQL joins still succeed — without leaking protected market limits.

---

## 📊 Summary Security Matrix

| Persona | Entra ID Mapping | Target Object | RLS Applied? | DDM Applied? | Quarantine Enforced? |
| --- | --- | --- | --- | --- | --- |
| **Automated CI/CD** | `spn-sovereignshield-cicd` | All Assets (Owner) | No — *requires* `sg-sovereignshield-admin` membership | No | No |
| **System Admin** | `sg-sovereignshield-admin` | `lbs_sdmx_history`, `lbs_micro_transactions` | No (Full Access) | No (Sees Raw Values) | No (Sees All Batches) |
| **National Submitter** | `sg-sovereignshield-submitter-*` | `lbs_sdmx_history`, `lbs_micro_transactions` | **Yes** (Sovereign Only, both tables) | No (Sees Raw Values) | No (Sees Own `QUARANTINE` + `FAILED_RULE_ID`) |
| **External Researcher** | `sg-sovereignshield-researchers` | `v_lbs_sdmx_published` | Permissive (view is global) | **Yes** (Masks `C` & `N` to `NULL`) | **Yes** (`PUBLISHED` **and** `IS_CURRENT`) |