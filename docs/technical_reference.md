# Technical Reference — implementation detail

The full implementation narrative for SovereignShield: compute isolation, the
Triple-Lock security matrix, the atomic quarantine engine, SCD2 mechanics, the
dissemination gateway, and anonymous access.

This is the *reference*, not the *tour*. If you are reading the codebase for the
first time, start with [technical_guide.md](technical_guide.md), which sequences
these topics into a reading order and tells you which parts matter most.

**Related:**
[README](../README.md) ·
[Reading guide](technical_guide.md) ·
[Scaling & stress testing](technical_guide.md) ·
[Onboarding playbook](ENTERPRISE_ONBOARDING_PLAYBOOK.md) ·
[Architecture diagrams](ARCHITECTURE_DIAGRAMS.md)

---

## 1. Compute isolation and cost optimisation

Unity Catalog will not evaluate RLS or DDM on `SINGLE_USER` compute — that mode permits direct memory access that could bypass the policy engine. The execution cluster is therefore pinned to `data_security_mode: USER_ISOLATION`, and the cost profile is tuned underneath that constraint rather than around it.

| Setting | Sandbox value | Rationale |
| --- | --- | --- |
| `spark_version` | `18.x-scala2.13` | Latest LTS — required for single-node `USER_ISOLATION` support |
| `num_workers` | `0` | Single Node: driver-only, no worker fleet to provision or pay for |
| `custom_tags.ResourceClass` | `SingleNode` | Signals the single-node profile to the Databricks control plane |
| `spark.master` | `local[*, 4]` | Executes in-driver with 4 retry attempts |
| `node_type_id` | `Standard_DS3_v2` | Stays clear of restrictive `DSv5` family core quotas |
| `availability` | `SPOT_WITH_FALLBACK_AZURE` | Spot pricing with automatic on-demand fallback if evicted |
| `data_security_mode` | `USER_ISOLATION` | Non-negotiable prerequisite for RLS/DDM enforcement |

Spot eviction is safe because the pipeline is fully idempotent: a re-run reproduces the same end state.

**Single-node is a default, not a ceiling.** The envelope is owned by a Terraform cluster policy in [`terraform/modules/databricks_workspace/compute.tf`](../terraform/modules/databricks_workspace/compute.tf); raising `worker_count_max`, switching `node_type_id` to a memory-optimised family and setting `enable_photon = true` widens it without touching pipeline code. See [technical_guide.md § Pass 6a](technical_guide.md) for the full sizing blueprint and the reasoning behind each lever.

* **Immutable execution:** scripts run via `spark_python_task` against the synchronised `src/` workspace directory, avoiding intermediate `.whl` compilation.

---

## 2. Dynamic asset execution in PySpark

A `spark_python_task` entry script is executed by Databricks via `exec(compile(source, filename, 'exec'))`. This creates two distinct hazards that must both be handled:

* `__file__` is **never bound**, so anchoring paths to it raises `NameError`.
* The working directory is **not** the bundle root, so `os.getcwd()` alone is equally unreliable.

Only the *entry script* is affected. Imported modules (such as `sdmx_rule_validator`) load through the normal import machinery and do have `__file__`.

`apply_security.resolve_sql_path()` therefore walks an ordered list of candidates, exploiting the fact that the path handed to `compile()` survives inside the code object:

```python
module_file = globals().get("__file__")          # local runs and imports
frame = inspect.currentframe()                   # frame.f_code.co_filename == the real workspace path
sys.argv[0]                                      # some task launchers
os.path.join(os.getcwd(), "src"), os.getcwd()    # last-resort fallbacks
```

Resolution is deliberately **lazy** (inside a function, not at module import). Evaluated at import time, the failure would fire before `main()` could ever apply a fallback.

---

## 3. SDMx observation semantics

The pipeline honours two SDMx conventions that are easy to get wrong and that materially change validation behaviour:

* **Values are signed.** LBS positions are legitimately negative as well as positive. A negative observation is never, by itself, a validation failure.
* **Zeros are not reported.** A position that nets to exactly zero is dropped after aggregation rather than published as a `0` observation.

Because values are signed, the disclosure-control dominance rule is computed on **absolute** contributions (`|bank| / Σ|bank|`). A signed share would divide by zero on offsetting positions and could exceed `1`.

**Frequency is a dimension, not a constant.** Segment 1 of the key is `FREQ`. LBS is collected quarterly (`Q`), but a statistical hub holds annual (`A`), semi-annual (`S`), quarterly and monthly (`M`) collections in the same history table, with reporting-period labels shaped per cadence (`2026`, `2026-S1`, `2026-Q1`, `2026-03`).

---

## 4. The Zero-Trust Triple-Lock security matrix

Security is centralised at the Unity Catalog **metastore** level rather than in pipeline code — the same obligations application layers enforce today, relocated one layer down. Because the policy is attached to the object rather than the query, it applies identically whether the caller arrives via PySpark, a SQL warehouse, Power BI, or an ad-hoc JDBC connection. There is no code path that can "forget" to apply it.

| | **Lock 1 — RLS** | **Lock 2 — DDM** | **Lock 3 — Quarantine View** |
| --- | --- | --- | --- |
| **Object** | `fn_rls_multi_persona_lock`<br/>`fn_rls_micro_country_lock` | `fn_ddm_obs_conf_mask` | `v_agg_sdmx_published` |
| **Binding** | `WITH ROW FILTER ... ON (TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF)`<br/>`ON (reporting_country)` | `OBS_VALUE DOUBLE MASK ... USING COLUMNS (OBS_CONF, TIME_SERIES_CODE)` | `CREATE OR REPLACE VIEW` |
| **Granularity** | Row | Cell | Result set |
| **Threat addressed** | Cross-border leakage, unpublished-state leakage | Confidential value disclosure | Unvalidated data reaching publication |
| **Effect** | Non-matching rows disappear | `OBS_VALUE` → `NULL` | `QUARANTINE` / superseded rows invisible |

### Lock 1 — Multi-column row-level security (sovereignty)

`fn_rls_multi_persona_lock` evaluates **three columns simultaneously** — the SDMx key, the batch lifecycle state, and the confidentiality flag. Filtering on the key alone would be insufficient the moment the data became publicly reachable: a public visitor asking for Canadian series would receive Canada's quarantined and confidential rows as readily as its published ones.

Segment 9 of the 11-dimension composite key is the reporting jurisdiction:

```text
FREQ . L_MEASURE . L_POSITION . L_INSTR . L_DENOM . L_CURR_TYPE
     . L_PARENT_CTY . L_REP_BANK_TYPE . L_REP_CTY . L_CP_SECTOR . L_CP_COUNTRY
                                            ▲
                                       segment 9  →  e.g.  Q.S.C.B.CAD.D.CA.A.CA.B.5J
```

The persona matrix the filter implements:

| Entra ID group | Visible rows |
| --- | --- |
| `sg-sovereignshield-admin` | `1 = 1` — every jurisdiction, every lifecycle state |
| `sg-sovereignshield-submitter-ca` / `-us` | **Own** segment-9 rows in full, including `QUARANTINE` and `C`/`N`; **other** jurisdictions only where `BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'` |
| `sg-sovereignshield-researchers` | `BATCH_STATUS = 'PUBLISHED'`, all jurisdictions — confidential values arrive masked |
| `sg-sovereignshield-public` | `BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'` |
| *no recognised membership* | `FALSE` — zero rows |

Four implementation details are load-bearing:

* **`try_element_at`, never `element_at`.** Under ANSI mode an out-of-range index raises `INVALID_ARRAY_INDEX`. Because a row filter is evaluated on *every row of every query*, one malformed key would abort **all** access to the table — converting a data-quality defect into a total outage. `try_element_at` returns `NULL`, and a `coalesce` turns that into `FALSE`, so the predicate fails **closed**.
* **Tiers compose with `OR`, not `CASE`.** A `CASE` expression stops at its first matching branch, so a Bank of Canada analyst who is also a researcher would be silently downgraded to whichever branch happened to be written first. Composing the tiers as a disjunction makes entitlement additive — a principal receives the union of their memberships.
* **The public tier is a group, not an absence.** The fail-closed default returns zero rows, so "unauthenticated" cannot be a fall-through case. The portal's proxy service principal is an explicit member of `sg-sovereignshield-public`, which means the anonymous entitlement is auditable in Entra ID like any other.
* **Defense in depth on the raw ledger.** `fn_rls_micro_country_lock` applies sovereign isolation to `lbs_micro_transactions.reporting_country`, and grants neither researchers nor the public tier any access at all. Protecting only the aggregate would leave the institution-level source fully exposed.

### Lock 2 — Dynamic data masking (confidentiality)

`fn_ddm_obs_conf_mask(obs_val DOUBLE, obs_conf STRING, time_series_code STRING)` is bound via `USING COLUMNS (OBS_CONF, TIME_SERIES_CODE)`, letting the mask branch on *different* columns than the one it redacts. Observations flagged Confidential (`C`) or Non-publishable (`N`) resolve to `NULL` for unprivileged readers.

* **Why the key is an input.** Without `TIME_SERIES_CODE` the function knows a value is confidential but not *whose* it is, so any submitter membership would unmask every jurisdiction's restricted cells. The mask therefore repeats the segment-9 test, and the fixture includes restricted rows in multiple jurisdictions.
* **Why `NULL` and not `'xxx'`:** a masking function must return the column's own type, and `OBS_VALUE` is a `DOUBLE`. A string sentinel is not representable.
* **Privilege ordering:** administrators and the owning submitter are evaluated *before* the confidentiality branch, so an entitled reader always sees the true value.
* **Structural density preserved:** the row still exists with all its dimensions intact, so researcher joins and dimensional counts remain correct — only the metric is withheld. The portal surfaces this explicitly, reporting how many values a query had withheld rather than silently returning blanks.

### Lock 3 — Quarantine view isolation (integrity)

The published view provides a uniform BI surface and gates on both publication
state and temporal currency:

```sql
CREATE OR REPLACE VIEW v_agg_sdmx_published AS
SELECT * FROM agg_sdmx_history
WHERE BATCH_STATUS = 'PUBLISHED' AND IS_CURRENT = true;
```

Both predicates are required. `BATCH_STATUS` alone would expose superseded historical versions; `IS_CURRENT` alone would expose active-but-rejected data.

### Supporting guarantees

* **Target catalog:** uses the pre-provisioned workspace catalog (`dbw_sovereignshield`), avoiding the need to grant Metastore Admin rights to the Service Principal.
* **Non-destructive, idempotent DDL:** `unity_catalog_triple_lock.sql` runs as the *first* task of *every* execution, so it must never drop the historical tables — doing so silently erases the entire SCD2 lineage. The script uses `CREATE TABLE IF NOT EXISTS` and a detach → replace → re-attach sequence, because Unity Catalog refuses to replace a function bound to a live row filter or column mask. Statements that legitimately fail on one lifecycle path (fresh create vs. re-apply) are annotated `-- @tolerate-failure` and skipped; every other failure aborts the deployment so the platform is never left partially secured.
* **Absolute SPN ownership:** the deployment pipeline executes via CI/CD, so the Service Principal assumes ownership of all created tables, views, and functions, stripping direct governance from individual developers.

> **Deployment prerequisite:** the pipeline Service Principal **must** be a member of `sg-sovereignshield-admin`. Ownership does not exempt a principal from a row filter. The SCD2 engine reads the target table to locate records to expire; if RLS hid those rows, the merge would treat every row as new — silently duplicating history and never closing prior versions. This fails without raising an error.

---

## 5. The atomic batch quarantine engine

BIS statistical submissions are accepted or rejected **as an indivisible unit**. Partial publication is not merely undesirable — it is incoherent: the aggregates that reconcile depend on the components that did not, so publishing the passing subset would emit an internally contradictory dataset.

`SDMxRuleValidator` parses the official consistency checks from `docs/reference_standards/checks_lbs.xls` at runtime — rules are **metadata, not code** — then evaluates them and applies the verdict atomically per `(reporting_country, date_scope)`:

| Batch outcome | `QUALITY_STATUS` | `BATCH_STATUS` | `FAILED_RULE_ID` |
| --- | --- | --- | --- |
| **Any** record in the reporting-period batch fails | `FAIL` on **every** row | `QUARANTINE` | Sorted union of all violated check codes |
| All records pass | `PASS` | `PUBLISHED` | `NULL` |

The validator is the single source of truth for these three columns; no downstream stage overrides them. There is no manual approval step and no intermediate `UNDER_REVIEW` state.

**Failure isolation is per-jurisdiction.** Grouping on `(reporting_country, date_scope)` means a Canadian reconciliation break quarantines Canada's period and nothing else — the US and UK submissions in the same run publish normally. Sovereign failure domains do not cascade.

### Prior-state preservation

The critical property: **a rejected revision never degrades what consumers can already see.** The merge engine splits the incoming batch on `BATCH_STATUS` before touching the target.

| Incoming | Prior active record | Row written | Visible in `v_agg_sdmx_published` |
| --- | --- | --- | --- |
| `PUBLISHED` (changed) | Expired → `IS_CURRENT = false` | `IS_CURRENT = true` | The new value |
| `PUBLISHED` (unchanged) | Untouched | None | Unchanged |
| `QUARANTINE` | **Untouched — remains `IS_CURRENT = true`** | Audit row, `IS_CURRENT = false`, `VALID_TO = VALID_FROM` | **The last valid value** |

Quarantined rows are excluded from both the expire-merge *and* the scoped logical delete. A failed resubmission therefore degrades to **stale data, never to missing data** — the rejection is fully recorded for audit and diagnosis, while the published series continues uninterrupted.

Replay is safe: a `left_anti` join on natural key + `version_hash` prevents a re-run from stacking duplicate audit rows.

### Demonstrable behaviour

`run_pipeline()` executes two cycles in sequence so the guarantee is directly observable rather than asserted:

| Cycle | CA | US | GB |
| --- | --- | --- | --- |
| `baseline` | 4 rows `PUBLISHED` | 4 rows `PUBLISHED` | 14 rows `PUBLISHED` |
| `revision` | 4 rows `QUARANTINE` (`LBS_CC01`) | 4 rows `QUARANTINE` (`LBS_CC01`) | 14 rows `QUARANTINE` (`LBS_CC02`, `LBS_CC:04`) |

After both cycles, all 22 baseline observations remain active and unmodified;
the 22 revision observations remain audit-only quarantine rows.

---

## 6. SCD2 historisation mechanics

The merge against `agg_sdmx_history` runs in four stages, keyed on `(TIME_SERIES_CODE, DATE, AGG_CODE)`:

1. **Expire changed records** *(published only)* — matches where `target.version_hash != source.version_hash`, setting `IS_CURRENT = false` and `VALID_TO = current_timestamp()`.
2. **Insert new active records** *(published only)* — written with `IS_CURRENT = true` and `VALID_TO = 9999-12-31T00:00:00`, an explicit end-of-time sentinel rather than `NULL` so range predicates need no special-casing.
3. **Append quarantine audit rows** — recorded with `IS_CURRENT = false` and `VALID_TO = VALID_FROM`, deliberately bypassing stage 1.
4. **Scoped logical delete** — closes series that existed previously but are absent from the current submission.

Three details prevent subtle corruption:

* **`version_hash` sentinel.** The payload fingerprint coalesces each component against `\u0000NULL`, not `""`. With an empty-string default, a genuine `NULL` and an empty value would hash identically and a real revision could be missed entirely.
* **Post-insert re-read.** Stage 4 re-reads the target rather than reusing the pre-insert snapshot, which would otherwise immediately expire the rows just written in stage 2.
* **Scope restriction.** Stage 4 is confined to the `(reporting_country, DATE)` pairs present in the *published* portion of the batch. Without it, submitting Canada's period would logically delete every other jurisdiction's series.

---

## 7. The public data portal and SDMx REST gateway

The locks above are only interesting if something actually exercises them from outside the workspace. `src/api_gateway.py` is a single FastAPI process that serves both the REST API under `/api/v1` and a BIS-style filter dashboard at `/`, deployed as a Databricks App.

**The gateway chooses an identity. It never chooses rows.** There is no persona branch anywhere in the serving code: the SQL it builds is deliberately naive about confidentiality and lifecycle state, and Unity Catalog narrows the result. If the gateway were compromised outright, the metastore would still refuse to hand a quarantined or confidential observation to an unentitled caller.

| Caller | Identity used | Carrier |
| --- | --- | --- |
| Signed-in workspace user | Their own OAuth token | `X-Forwarded-Access-Token`, injected by the Databricks Apps runtime |
| Direct API client | Their own OAuth token | `Authorization: Bearer` |
| Signed-in Container Apps visitor | Their own OAuth token | Browser reads same-origin `/.auth/me`, retains the token in memory, and sends `Authorization: Bearer` |
| Anonymous Container Apps visitor | `spn-sovereignshield-public` | Azure client-secret authentication from Key Vault references |

Token validation is delegated rather than reimplemented: the gateway resolves the token against the workspace SCIM `me` endpoint, so an expired, revoked, or forged token fails there. No JWT signature verification is hand-rolled, and the token itself is never cached — only a SHA-256 digest of it, keyed to a short-lived identity lookup.

### Endpoints

| Route | Purpose |
| --- | --- |
| `GET /api/v1/search` | Filter by `frequency`, `parent_country`, `reporting_country`, `counterpart_sector`, `counterpart_country`, `currency`, `position`, `instrument`, `date_from`, `date_to` |
| `GET /api/v1/facets` | Distinct code values for the filter cards — already persona-scoped, so a visitor cannot discover that a code exists if the filter hides every row carrying it |
| `GET /api/v1/export/sdmx-ml` | SDMX-ML 3.0 structure-specific message |
| `GET /api/v1/export/sdmx-json` | SDMX-JSON 2.0.0 data message |
| `GET /api/v1/export/csv` | SDMX-CSV 2.0.0, or `?format=tidy` for a plain analyst CSV |
| `GET /api/v1/whoami` | The security context the portal banner renders |
| `GET /api/v1/health` | Catalog connectivity, backend mode, and structure availability |
| `GET /api/v1/auth-diagnostics` | Presence-only Easy Auth diagnostics; never returns token or claim values |

Every caller-supplied value is bound as a query parameter, and code values are additionally constrained to `[A-Za-z0-9_]{1,12}` before they reach the warehouse — parameter binding already prevents injection, the pattern check keeps malformed input from being blamed on the metastore.

**Cross-frequency dissemination.** `frequency` is a first-class filter card, presented first because it partitions the catalogue: an analyst comparing a monthly series against a quarterly aggregate of the same position is making a category error, and the filter is the cheapest place to prevent it.

### SDMx 3.0 serialization

`src/sdmx_ml_exporter.py` replaces the flat CSV export with the formats a statistical portal is expected to speak, all reported against the BIS Data Portal dataflow `BIS:WS_LBS_D_PUB(1.0)`.

* **SDMX-ML 3.0.** SDMX 3.0.0 **removed** the Generic Data format, so `StructureSpecificData` is the only XML data message the standard still defines; the `output_type` argument exists for forward compatibility and rejects anything else rather than silently emitting a 2.1-era payload. Serialization runs through `pysdmx`, which writes against the published schemas, and the emitted document is round-tripped through the reader before it is returned — an invalid message is caught here, not by the receiving institution.
* **Degraded mode.** The BIS structure endpoint is a live third-party HTTP dependency. It is fetched once and cached for the life of the process, and a dependency-free ElementTree writer stands behind it so an export never fails because BIS is having a bad morning. Messages produced that way are flagged `Test` so a consumer can tell they were written without structure validation.
* **SDMX-JSON 2.0.0** for browsers and **SDMX-CSV 2.0.0** for tabular consumers — the latter carrying the standard's `STRUCTURE,STRUCTURE_ID,ACTION` prefix so a file is self-describing rather than depending on an out-of-band agreement about column order.

A masked observation is serialized as an **absent** value, never as zero. Under SDMx semantics those mean entirely different things, and conflating them would turn a confidentiality control into a data-quality defect.

### Deploying the portal

```bash
databricks bundle deploy -t dev --var="warehouse_id=<sql-warehouse-id>"
databricks bundle run sovereignshield_portal -t dev
```

The bundle uploads `./src` as the app source, so `src/app.yaml` and `src/requirements.txt` travel with the modules they launch. The app's dependency set is deliberately separate from the repository root manifest: the portal has no use for PySpark, Delta or the Excel rulebook parsers, and installing them would add hundreds of megabytes to every deployment.

The app's own service principal must be a member of `sg-sovereignshield-public`. Without it the fail-closed default returns zero rows and the portal renders empty for every anonymous visitor.

---

## 8. Genuinely anonymous access via Azure Container Apps

A Databricks App always sits behind workspace SSO. Its "public" tier is therefore an *authenticated visitor holding no sovereign entitlement* — which proves the persona matrix, but not the anonymous case that a real dissemination portal has to survive.

Azure Container Apps closes that gap by running the same image with external
ingress. The Terraform module provisions anonymous access. The script path also
supports optional Easy Auth sign-in. Choose one owner for the deployment because
both paths use the same resource names.

```powershell
cd terraform
terraform apply -var="deploy_dissemination_gateway=true" -var="gateway_image=<acr>/sovereignshield-portal:latest"
terraform output -raw dissemination_gateway_url
```

The module uses a **user-assigned** managed identity rather than system-assigned. That is not a preference: a system-assigned identity only exists after the container app is created, but the app cannot start until it can resolve its `keyvaultref` secrets, which needs the role assignment, which needs the identity. First apply deadlocks.

`sh/container_apps_deploy.ps1` performs the same deployment imperatively for the quickstart path, and additionally builds the image with `az acr build`:

```powershell
./sh/container_apps_deploy.ps1 -KeyVaultName <vault-name> `
    -DatabricksHost <workspace-url-without-https> `
    -WarehouseId <sql-warehouse-id>
```

Nothing about the security model changes — only who can knock. The row filter remains the sole arbiter of what is returned, and the container holds no entitlement of its own.

| Concern | How the deployment handles it |
| --- | --- |
| Credentials | Public proxy credentials use Key Vault references. The Easy Auth SAS is generated transiently, stored as a Container App secret through a Windows-safe quoted handoff, and never written to tracked files or logs. |
| Image build | `az acr build` — built in Azure, so no local Docker daemon and no image pushed from a workstation |
| Container privileges | Runs as an unprivileged UID with only the four serving modules and the template directory copied in. The ingestion job, the synthetic data, and the BIS rulebook workbook are not in the serving path and are not in the image. |
| Elevated personas | `-EnableEntraSignIn` configures Easy Auth with `AllowAnonymous`, ID-token issuance, admin consent, and `openid profile offline_access AzureDatabricks/user_impersonation`. A Blob-backed token store retains provider tokens. The browser reads same-origin `/.auth/me`, keeps the access token in memory, and attaches it to API requests. |
| Token-store integrity | A dedicated storage account holds Easy Auth session material. The Windows script preserves the complete SAS through a quoted environment-variable handoff, validates `se`, `sp`, `spr`, `sv`, `sr`, and `sig`, and restarts the active revision after secret updates. |

The script configures the Entra application, client service principal, delegated
permission, admin consent, redirect URI, login parameters, token store, and
revision restart. No portal-only authentication step is required.

The deployment finishes by printing the check worth running first:

```bash
curl -s "https://<fqdn>/api/v1/search?limit=5" | jq '.observations[] | {BATCH_STATUS, OBS_CONF}'
```

Every observation returned to an anonymous caller must carry `BATCH_STATUS=PUBLISHED` and `OBS_CONF=F`. Anything else means the proxy principal picked up a group membership it should not have.
