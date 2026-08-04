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
* **Security Bind:** No individual human developer holds mutation or DDL execution rights in production. All structural changes must pass through version control and be deployed by this identity.

### 2. System Administrators

* **Entra ID Group:** `sg-sovereignshield-admin`
* **Role:** Internal data platform administrators and principal data engineers troubleshooting the pipeline.
* **Access Level:** Full Read Access to the raw historical table (`lbs_sdmx_history`).
* **Security Bind:** Explicitly bypasses all Row-Level Security (RLS) filters and Dynamic Data Masking (DDM) policies. Can view all sovereign data and all unmasked `OBS_VALUE` metrics globally.

### 3. National Analysts / Submitters

* **Entra ID Group:** `sg-sovereignshield-submitter-<country_code>` (e.g., `sg-sovereignshield-submitter-ca`)
* **Role:** Regional data stewards responsible for validating and analyzing their specific jurisdiction's SDMx submissions.
* **Access Level:** Restricted Read Access to the raw historical table (`lbs_sdmx_history`).
* **Security Bind (RLS):** Restricted by Row-Level Security. The Unity Catalog policy dynamically parses the 9th index of the `TIME_SERIES_CODE` and matches it to the user's group suffix. They can *only* query rows belonging to their reporting country.
* **Security Bind (DDM):** Bypasses Dynamic Data Masking for their own sovereign data. They can see raw `OBS_VALUE` numbers even if the record is flagged as Confidential (`C`) or Non-publishable (`N`).

### 4. External Researchers

* **Entra ID Group:** `sg-sovereignshield-researchers`
* **Role:** Macroeconomic researchers, cross-regional analysts, and public data consumers.
* **Access Level:** Highly Restricted View Access. They are denied direct access to `lbs_sdmx_history` and must query the abstraction layer: `v_lbs_sdmx_published`.
* **Security Bind (The Quarantine Gate):** The view strictly filters for `BATCH_STATUS = 'PUBLISHED'` and `IS_CURRENT = true`. Unvalidated or quarantined batches are physically invisible.
* **Security Bind (DDM):** Fully bound by Dynamic Data Masking. If `OBS_CONF` is `C` or `N`, the `OBS_VALUE` is dynamically masked to `'xxx'`. This preserves structural dimensional density (allowing complex SQL joins to succeed) without leaking protected market limits.

---

## 📊 Summary Security Matrix

| Persona | Entra ID Mapping | Target Object | RLS Applied? | DDM Applied? | Quarantine Enforced? |
| --- | --- | --- | --- | --- | --- |
| **Automated CI/CD** | `spn-sovereignshield-cicd` | All Assets (Owner) | No | No | No |
| **System Admin** | `sg-sovereignshield-admin` | `lbs_sdmx_history` | No (Full Access) | No (Sees Raw Values) | No (Sees All Batches) |
| **National Submitter** | `sg-sovereignshield-submitter-*` | `lbs_sdmx_history` | **Yes** (Sovereign Only) | No (Sees Raw Values) | No (Sees All Batches) |
| **External Researcher** | `sg-sovereignshield-researchers` | `v_lbs_sdmx_published` | N/A (Global View) | **Yes** (Masks `C` & `N`) | **Yes** (Only `PUBLISHED`) |