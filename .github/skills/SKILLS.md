# 🧭 SovereignShield — Platform Capability Matrix

**SovereignShield** explores Zero-Trust for **SDMx 3.0 statistical submissions to an international body** — national central banks reporting confidential banking data into the BIS Locational Banking Statistics collection. The perimeter here is not a network boundary but a *national* one, and it is legal rather than technical. Institutions already enforce that boundary rigorously through specialised SDMx software and operational protocol; every capability below explores what it looks like when the same boundary is additionally expressed in the data platform itself.

This matrix documents the **operational capabilities the platform actually implements**, each mapped to the artifact that enforces it. It is the authoritative index for agents and reviewers: every row below corresponds to code in this repository, not to aspirational scope.

**Namespace:** `dbw_sovereignshield.sovereign_shield` · **Runtime:** Databricks 18.x LTS · **Standard:** SDMx 3.0 / BIS LBS

![Policy as a Metastore Object — promotion plane, the Terraform/pipeline ownership boundary, a data plane with quarantine isolation, and a consumption band, all resolving into a Unity Catalog enforcement point that maps five personas ending in "no group — zero rows, fails closed".](../../docs/sovereign-shield_technical_vision.jpg)

*Every capability below appears somewhere in this diagram. If a claim here has no
counterpart in the image, one of the two is out of date.*

---

## 0. 📚 Skill index

| Skill | Owns | Read it when |
| --- | --- | --- |
| [`mvsd_specification.md`](mvsd_specification.md) | The synthetic data contract: authoritative BIS LBS dimensions, codelist semantics, required test coverage, and the export rules that let an org hand over structure without handing over records | Adding a dimension, a jurisdiction, or a test fixture |
| [`persona_security_matrix.md`](persona_security_matrix.md) | Who may read which rows, and the exact SQL that decides it | Changing an entitlement or adding a persona |
| [`triple_lock_security.md`](triple_lock_security.md) | The three enforcement objects and their DDL lifecycle | Editing `unity_catalog_triple_lock.sql` |
| [`sdmx_lbs_validation.md`](sdmx_lbs_validation.md) | Runtime rulebook compilation and the atomic batch verdict | Touching the validator or the check workbook |
| [`scd2_engine.md`](scd2_engine.md) | The four-stage merge and the quarantine state machine | Touching historisation |
| [`contractor_zero_trust_workflow.md`](contractor_zero_trust_workflow.md) | The delivery pattern: specification / execution / promotion boundaries and revocation | Onboarding a contributor, or reviewing the security posture |

Every row in the sections below corresponds to code in this repository, not to aspirational scope.

---

## 1. 📊 SDMx 3.0 & BIS LBS Standards Compliance

| Capability | Implementation | Artifact |
| --- | --- | --- |
| SDMx 3.0 XML generation | Structure-specific messages emitted via `pysdmx` | `generate_sovereign_submissions.py` |
| DSD resolution | Live `BIS_LBS` dimension fetch, with a pinned 11-dimension fallback when the registry is unreachable | `sdmx_rule_validator.py` |
| 11-dimension composite key | `FREQ.L_MEASURE.L_POSITION.L_INSTR.L_DENOM.L_CURR_TYPE.L_PARENT_CTY.L_REP_BANK_TYPE.L_REP_CTY.L_CP_SECTOR.L_CP_COUNTRY` | `scd2_merge_engine.py` |
| Signed observations | Negative positions are valid (asset vs. liability direction) and are never a failure on their own | Aggregation layer |
| Zero suppression | Positions netting to exactly `0` are filtered, never published as an observation | Aggregation layer |
| Confidentiality escalation | Most-restrictive-wins rollup: any `C` → `C`; else any `N` → `N`; else `F` | Aggregation layer |
| Codelist enforcement | Sector codes constrained to BIS breakdowns `{B,M,F,C,G,H}` + aggregates `{A,N,U}` | `_assert_valid_sector_codes` |
| Disclosure control | Dominance computed on **absolute** contributions (`\|bank\| / Σ\|bank\|`), threshold `0.60` → `OBS_CONF = 'N'` | `aggregate_micro_to_macro` |

> Signed values make naive dominance arithmetic unsafe: a signed denominator can reach zero on offsetting positions and yield shares above `1`. Absolute contributions are the only correct basis.

---

## 2. 🧪 Atomic Batch Validation

| Capability | Implementation |
| --- | --- |
| **Metadata-driven rules** | BIS consistency checks are parsed from `docs/reference_standards/checks_lbs.xls` at runtime and compiled into predicates — rules are data, not code, so a workbook update requires no deployment |
| **Rule coverage** | `LBS_CC01`–`LBS_CC03` (no colon) and `LBS_CC:04`–`LBS_CC:21` (with colon); the inconsistent source formatting is preserved verbatim, since normalizing it would silently drop rules |
| **Check semantics** | Purely arithmetic reconciliation: an aggregate code must equal the sum of its component codes on the same dimension, within `1e-4` |
| **Wildcard handling** | The code `ISO` matches any value on its dimension — making `L_CP_COUNTRY` unsuitable for scenario isolation, as `LBS_CC:11`–`:21` target it with `ISO` |
| **Atomic verdict** | Grouped by `(L_REP_CTY, DATE)`: any single failure sets `QUALITY_STATUS = FAIL`, `BATCH_STATUS = QUARANTINE`, and a `FAILED_RULE_ID` union across **every** row of that country-quarter |
| **Failure isolation** | Quarantine is scoped per jurisdiction — one country's break never blocks another's publication in the same run |
| **Arity guard** | Segment counts are verified per row before splitting; a ragged split would pad short keys and shift every subsequent dimension, misaligning the whole batch |
| **Normalization** | All dimension values `strip().upper()`-ed on both sides of every comparison |
| **Empty-batch tolerance** | An empty input returns a correctly-shaped empty frame — a non-reporting quarter is a valid state, not an error |
| **Single source of truth** | The validator alone authors `QUALITY_STATUS`, `BATCH_STATUS`, and `FAILED_RULE_ID`; no downstream stage overrides them |

Partial publication is rejected by design: aggregates that reconcile depend on components that did not, so publishing only the passing subset would emit an internally contradictory dataset.

---

## 3. 🛡️ Unity Catalog Fine-Grained Access Control

| Lock | Object | Binding | Granularity |
| --- | --- | --- | --- |
| **RLS (macro)** | `fn_rls_lbs_multi_persona_lock` | `WITH ROW FILTER ... ON (TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF)` | Row |
| **RLS (micro)** | `fn_rls_micro_country_lock` | `WITH ROW FILTER ... ON (reporting_country)` | Row |
| **DDM** | `fn_ddm_obs_conf_mask` | `OBS_VALUE DOUBLE MASK ... USING COLUMNS (OBS_CONF, TIME_SERIES_CODE)` | Cell |
| **Quarantine View** | `v_lbs_sdmx_published` | `BATCH_STATUS = 'PUBLISHED' AND IS_CURRENT = true` | Result set |

**Persona resolution** — evaluated at query time via `is_account_group_member`:

| Persona | Entra ID group | Reaches | RLS | DDM | Quarantine gate |
| --- | --- | --- | --- | --- | --- |
| CI/CD | `spn-sovereignshield-cicd` | All assets (owner) | Bypass — *requires* admin group membership | Bypass | No |
| Admin / auditor | `sg-sovereignshield-admin` | Both base tables | Bypass | Bypass | No |
| Submitter | `sg-sovereignshield-submitter-<cc>` | Both base tables | **Enforced** | Bypass for own segment 9 only | Sees own `QUARANTINE` + `FAILED_RULE_ID` |
| Researcher | `sg-sovereignshield-researchers` | History table, `PUBLISHED` only | **Enforced** | **Enforced** (`C`/`N` → `NULL`) | **Enforced** |
| Public | `sg-sovereignshield-public` | History table, `PUBLISHED` + `OBS_CONF = 'F'` | **Enforced** | Moot — no `C`/`N` row is visible | **Enforced** |
| *(no membership)* | — | Nothing | **Fails closed** | — | — |

Operational competencies exercised:

* **Policy-as-metastore-object.** Governance is attached to the table, not the query, so it applies identically across PySpark, SQL warehouses, BI tools, and ad-hoc JDBC. No code path can omit it.
* **ANSI-safe policy authoring.** Row filters must fail *closed*, not *loud*: `try_element_at` over `element_at`, because an exception raised inside a row filter aborts every query against the table and converts a data-quality defect into an outage.
* **Type-compatible masking.** A mask returns the masked column's own type — `OBS_VALUE` is `DOUBLE`, so `NULL` is the only valid redaction; a `'xxx'` sentinel is not representable.
* **Ownership ≠ exemption.** Object ownership does not lift a row filter. The pipeline SPN must hold admin group membership or the merge reads an empty target and silently duplicates history.
* **Defense in depth.** Protecting the aggregate while leaving the raw ledger open is not sovereignty; both tables carry filters.
* **Idempotent, non-destructive DDL.** Security re-executes on every run without erasing state: `CREATE TABLE IF NOT EXISTS` guards, detach → replace → re-attach sequencing for policy-bound functions, and per-statement `-- @tolerate-failure` markers with fail-fast defaults.

---

## 4. 🕰️ Delta Lake Historization (SCD Type 2)

| Capability | Implementation |
| --- | --- |
| Four-stage merge | Expire changed → insert active → append quarantine audit → scoped logical delete |
| Change detection | `version_hash` payload fingerprint, coalesced against a `\u0000NULL` sentinel so `NULL` and `""` cannot collide |
| End-of-time sentinel | Active rows carry `VALID_TO = 9999-12-31T00:00:00`, not `NULL`, so range predicates need no special-casing |
| **Fail-safe state machine** | Quarantined revisions append as audit-only rows (`IS_CURRENT = false`, `VALID_TO = VALID_FROM`) and are excluded from the expire-merge — the prior published record **stays active** |
| Replay idempotency | `left_anti` join on natural key + `version_hash` prevents duplicate audit rows across re-runs |
| Snapshot correctness | The logical-delete stage re-reads the target post-insert; reusing the pre-insert snapshot would immediately expire the rows just written |
| Blast-radius control | Logical delete is scoped to the `(reporting_country, DATE)` pairs in the published batch, so one jurisdiction's submission cannot retire another's series |
| Batch stamping | A single UTC timestamp per batch, with a row-width guard that names the offending `transaction_id` instead of surfacing an opaque `AXIS_LENGTH_MISMATCH` |

The governing principle: **validation failure degrades to stale data, never to missing data.**

---

## 5. ⚙️ IaC, Secrets & Orchestration

| Capability | Implementation |
| --- | --- |
| Declarative deployment | Databricks Asset Bundles; three ordered tasks with security provisioned **before** any data is written |
| Secret management | Azure Key Vault (`kv-sovereignshield-28083`); no credential literal in git, config, or disk |
| Session auth | **Dot-sourced** `pre_auth.ps1` — child-process invocation would discard the variables on return |
| Credential rotation | `kv_spn_remediation.sh` deletes the app registration, mints fresh credentials, and overwrites stored secrets |
| Compute topology | Single Node (`num_workers: 0`, `ResourceClass: SingleNode`, `spark.master: local[*, 4]`) on `Standard_DS3_v2` |
| Cost posture | `SPOT_WITH_FALLBACK_AZURE` — safe because the pipeline is idempotent and a re-run reproduces the same end state |
| Security mode | `USER_ISOLATION` — a hard prerequisite, as Unity Catalog will not evaluate RLS/DDM on `SINGLE_USER` compute |
| Immutable execution | `spark_python_task` against the synced `src/` directory, avoiding intermediate `.whl` builds |

---

## 6. 🧰 Engineering Practices & Failure-Mode Coverage

* **Runtime path resolution.** A `spark_python_task` entry script is run via `exec(compile(...))` and has no `__file__`, while `os.getcwd()` is not the bundle root. The true path is recovered from the code object (`inspect.currentframe().f_code.co_filename`) through an ordered, **lazily evaluated** candidate chain — evaluated at import time, the failure would fire before any fallback could run. Only the entry script is affected; imported modules load normally.
* **Silent-failure auditing.** Systematic review for defects that produce no error: destructive DDL inside an idempotent path, hash collisions between `NULL` and `""`, case-variant codes evading string-matched filters, and pre-insert snapshots driving post-insert decisions.
* **JVM-free local development.** SCD2 semantics are reproducible on pandas + `delta-rs` (`local_pandas_scd2.py`); Spark-path logic is exercised via `sys.modules` injection and mocking.
* **Test-integrity discipline.** Verification must call the real code path — reconstructing inputs by parsing source misses real defects, and a bare `except Exception: pass` can convert a genuine error into a false pass. Unexpected exceptions are allowed to propagate.
* **Empirical verification of identifiers.** Reference codes are confirmed against the live artifact rather than assumed; source workbooks contain inconsistencies that normalization would silently swallow.