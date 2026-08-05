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
    DATE STRING,                  -- Standardized observation period (e.g. '2026-Q1')
    IBS_AGG STRING,               -- Aggregation scope (e.g. 'LBSR')
    OBS_VALUE DOUBLE,             -- Aggregated numeric metric (signed; never zero)
    OBS_STATUS STRING,            -- Observation status flag
    OBS_CONF STRING,              -- Confidentiality flag ('F', 'N', 'C')
    QUALITY_STATUS STRING,        -- Validator verdict ('PASS' | 'FAIL')
    FAILED_RULE_ID STRING,        -- Comma-joined BIS check codes; NULL when clean
    BATCH_STATUS STRING,          -- Processing state ('PUBLISHED' | 'QUARANTINE')
    version_hash STRING,          -- SCD2 payload fingerprint
    VALID_FROM TIMESTAMP,         -- SCD2 Start Time
    VALID_TO TIMESTAMP,           -- SCD2 End Time (9999-12-31 sentinel while active)
    IS_CURRENT BOOLEAN            -- SCD2 Active Record Flag
) USING DELTA;

```

The validator emits these columns in a fixed order and the merge engine binds the result to an explicit `StructType` (`VALIDATED_MACRO_SCHEMA`) rather than relying on Spark's type inference — an all-`NULL` `FAILED_RULE_ID` column would otherwise be inferred as `void` and fail the merge.

---

## 🛡️ The BIS Rule Engine (`src/sdmx_rule_validator.py`)

Validation rules are **not hard-coded**. `SDMxRuleValidator` parses the official BIS consistency checks from `docs/reference_standards/checks_lbs.xls` at runtime and compiles each row into an executable predicate. Dimension names are resolved from the live `BIS_LBS` DSD via `pysdmx`, falling back to a pinned 11-dimension list when the registry is unreachable.

### 1. Composite Key Decomposition

The `TIME_SERIES_CODE` is decomposed into its 11 named dimensions:

```text
FREQ . L_MEASURE . L_POSITION . L_INSTR . L_DENOM . L_CURR_TYPE
     . L_PARENT_CTY . L_REP_BANK_TYPE . L_REP_CTY . L_CP_SECTOR . L_CP_COUNTRY

e.g.  Q.S.C.B.CAD.D.CA.A.CA.B.5J
```

* **Arity guard:** every key's segment count is verified per row *before* splitting. A ragged `str.split(expand=True)` silently pads short keys with `NaN` and shifts every subsequent dimension left, so a single malformed key would misalign the entire batch. A mismatch raises immediately, naming the offending code and its actual segment count.
* **Normalization:** all dimension values are `strip().upper()`-ed on both sides of every comparison, so case variance cannot cause a check to be skipped.

### 2. Aggregate Reconciliation Checks

Every rule is arithmetic, not semantic: for a given context, an **aggregate** code on one dimension must equal the **sum of its component** codes on that same dimension.

* **Rule identifiers:** `LBS_CC01`, `LBS_CC02`, `LBS_CC03` (no colon), and `LBS_CC:04` through `LBS_CC:21` (with colon). The inconsistent formatting comes from the source workbook and is preserved verbatim — matching on a normalized form would silently miss rules.
* **Wildcard semantics:** the code `ISO` in a rule definition means "any value on this dimension". Consequently `L_CP_COUNTRY` is a poor choice for isolating a test scenario, since `LBS_CC:11`–`LBS_CC:21` target it with `ISO` and will match arbitrary values.
* **Tolerance:** equality is asserted with `abs(lhs_sum - rhs_sum) < 1e-4` to absorb floating-point drift.
* **Dimensions never used as check targets:** `FREQ`, `L_MEASURE`, `L_POSITION`, `L_REP_CTY`. These are the safe axes for isolating a deliberate test scenario without tripping unintended rules.

The engine performs no semantic validation — no codelist membership, no sign checks, no plausibility bounds. Those concerns are enforced upstream in the aggregation layer (`_assert_valid_sector_codes`) and at the DDL layer.

### 3. SDMx Value Semantics

Two conventions materially change what counts as a failure:

* **Values are signed.** LBS positions record both asset and liability directions, so negative observations are entirely legitimate and are **never** a validation failure on their own.
* **Zeros are not reported.** A position netting to exactly zero is filtered out during aggregation rather than published as `0`.

### 4. Confidentiality Flag Elevation

Micro-transactions carry individual confidentiality tags; the macro `OBS_CONF` must reflect the most restrictive tag among its components.

* **The Rule:** any `C` in the group forces the macro record to `C`; failing that, any `N` forces `N`; otherwise `F`.
* **The Enforcement:** this guarantees the Unity Catalog masking policy (`fn_ddm_obs_conf_mask`) correctly identifies and masks protected values to `NULL` for unprivileged readers.

### 5. Empty Batch Handling

An empty input returns a correctly-shaped empty frame rather than raising. A quarter in which a jurisdiction reports nothing is a valid state, not an error.

---

## 🚧 The Quarantine Gate (`BATCH_STATUS`)

BIS submissions are accepted or rejected **as a whole**. A partially-published quarter is meaningless: the aggregates that reconcile depend on the components that did not.

The validator therefore applies its verdict atomically, grouping by `(L_REP_CTY, DATE)`:

| Batch outcome | `QUALITY_STATUS` | `BATCH_STATUS` | `FAILED_RULE_ID` |
| --- | --- | --- | --- |
| Any record in the country-quarter fails | `FAIL` on **every** row | `QUARANTINE` | Sorted union of every violated check code |
| All records pass | `PASS` | `PUBLISHED` | `NULL` |

There is no manual approval step and no `UNDER_REVIEW` state. The validator is the single source of truth for these three columns, and no downstream stage overrides them.

**The Security Bind:** the researcher-facing view hardcodes `WHERE BATCH_STATUS = 'PUBLISHED' AND IS_CURRENT = true`. Because quarantined rows are written as audit-only records (`IS_CURRENT = false`, `VALID_TO = VALID_FROM`) and never expire the previously published version, a rejected resubmission degrades gracefully: researchers continue to see the last valid state rather than a gap.