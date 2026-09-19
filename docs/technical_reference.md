# Technical Reference — implementation detail

The full implementation narrative for SovereignShield: compute isolation, the
Triple-Lock security matrix, the atomic quarantine engine, SCD2 mechanics, the
dissemination gateway, and anonymous access.

The [reading guide](technical_guide.md) provides an implementation reading order.
This reference defines the current contracts and their enforcement boundaries.

**Intake scope:** SDMx files are the international submission contract. Synthetic
bank micro-transactions exist solely as educational fixtures illustrating the
calculation of realistic observations; the demo ledger is not an institutional
intake requirement or system deliverable. Domestic granular-data collection is
outside this modeled exchange.

**Related:**
[README](../README.md) ·
[Reading guide](technical_guide.md) ·
[Scaling & stress testing](technical_guide.md) ·
[Onboarding playbook](ENTERPRISE_ONBOARDING_PLAYBOOK.md) ·
[Architecture diagrams](ARCHITECTURE_DIAGRAMS.md)

---

## 1. Compute isolation and cost optimisation

This deployment pins `USER_ISOLATION`. Dedicated compute supports governed access under specific runtime/serverless conditions; it is not a universal policy bypass. Verify the [current platform limitations](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/filters-and-masks/) for the selected engine.

| Setting | Sandbox value | Rationale |
| --- | --- | --- |
| `spark_version` | `18.x-scala2.13` | Runtime family used by the validated deployment |
| `num_workers` | `0` | Single Node: driver-only, no worker fleet to provision or pay for |
| `custom_tags.ResourceClass` | `SingleNode` | Signals the single-node profile to the Databricks control plane |
| `spark.master` | `local[*, 4]` | Executes in-driver with 4 retry attempts |
| `node_type_id` | `Standard_DS3_v2` | Stays clear of restrictive `DSv5` family core quotas |
| `availability` | `SPOT_WITH_FALLBACK_AZURE` | Spot pricing with automatic on-demand fallback if evicted |
| `data_security_mode` | `USER_ISOLATION` | Supported mode selected for this deployment; alternatives require runtime-specific validation |

Replay of the same archived submission is idempotent. After interruption, repair
the failed job tasks rather than regenerating arrivals: a new generator run creates
new submission identities even when values match.

**Single-node is a default, not a ceiling.** Terraform supplies the governed cluster
specification in [compute.tf](../terraform/modules/databricks_workspace/compute.tf).
Larger worker counts and Photon require approval. Driver-bound pandas XML parsing
and arithmetic checks do not become distributed by increasing workers.

The successful synthetic evaluation took about **75 minutes to provision including
prerequisites**, **30 minutes to tear down**, and **US$10 or less in Azure charges
for deploy/test/teardown**. These are reference-cycle observations, not production
capacity or cost guarantees; see [measurement scope](RELEASE_EVIDENCE.md#reference-evaluation-metrics).

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
* **Zeros are retained.** Genuine zero, missing input and a masked value are distinct. Measures use `DECIMAL(38,3)` with decimal half-up intake rounding; three places are the reference profile, not a universal SDMx requirement.

The educational synthetic generator illustrates classification using absolute
contribution shares and a 0.60 dominance threshold. This is not a complete
disclosure-control method or a required calculation by the receiving platform.

**Frequency is a dimension.** Segment 1 is `FREQ`; this BIS LBS fixture is quarterly
(`Q`). Generic stress fixtures use several cadence labels, but only values and
period shapes allowed by the pinned data contract are accepted as LBS submissions.

---

## 4. The Zero-Trust Triple-Lock security matrix

Unity Catalog table policies enforce row/value entitlements on supported query
paths independently of application predicates. Runtime/access-mode limitations,
privileged control-plane access, direct storage, gateway tokens and exports remain
explicit trust boundaries. Policies evaluate Databricks account groups; Entra
reconciliation during setup is not continuous deprovisioning.

| | **Lock 1 — RLS** | **Lock 2 — DDM** | **Lock 3 — Quarantine View** |
| --- | --- | --- | --- |
| **Object** | `fn_rls_multi_persona_lock`<br/>`fn_rls_micro_country_lock` | `fn_ddm_obs_conf_mask` | `v_agg_sdmx_published` |
| **Binding** | `WITH ROW FILTER ... ON (TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF)`<br/>`ON (reporting_country)` | `OBS_VALUE DECIMAL(38,3) MASK ... USING COLUMNS (OBS_CONF, TIME_SERIES_CODE)` | `CREATE OR REPLACE VIEW` |
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

| Databricks account group | Visible rows |
| --- | --- |
| `sg-sovereignshield-admin` | `1 = 1` — every jurisdiction, every lifecycle state |
| `sg-sovereignshield-submitter-ca` / `-us` | **Own** segment-9 rows in full, including `QUARANTINE` and `C`/`N`; **other** jurisdictions only where `BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'` |
| `sg-sovereignshield-researchers` | `BATCH_STATUS = 'PUBLISHED'`, all jurisdictions — confidential values arrive masked |
| `sg-sovereignshield-public` | `BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'` |
| *no recognised membership* | `FALSE` — zero rows |

Four implementation details are load-bearing:

* **`try_element_at`, never `element_at`.** Under ANSI mode an out-of-range index raises `INVALID_ARRAY_INDEX`. Because a row filter is evaluated on *every row of every query*, one malformed key would abort **all** access to the table — converting a data-quality defect into a total outage. `try_element_at` returns `NULL`, and a `coalesce` turns that into `FALSE`, so the predicate fails **closed**.
* **Tiers compose with `OR`, not `CASE`.** A `CASE` expression stops at its first matching branch, so a Canadian Regional Submitter (CA) who is also a researcher would be silently downgraded to whichever branch happened to be written first. Composing the tiers as a disjunction makes entitlement additive — a principal receives the union of their memberships.
* **The public tier is explicit.** The proxy principal belongs to `sg-sovereignshield-public` at Databricks account scope. No recognized group returns no entitled rows.
* **Educational ledger isolation.** `fn_rls_micro_country_lock` filters the synthetic bank micro-transaction ledger by country. Researchers and the public have no access. This additional demo object is not the international intake contract.

### Lock 2 — Dynamic data masking (confidentiality)

`fn_ddm_obs_conf_mask(obs_val DECIMAL(38,3), obs_conf STRING, time_series_code STRING)`
is bound via `USING COLUMNS (OBS_CONF, TIME_SERIES_CODE)`. After administrator and
own-country checks, only explicit `F` reveals a measure. Other flags, including
unknown or missing classifications, return `NULL`.

* **Why the key is an input.** Without `TIME_SERIES_CODE` the function knows a value is confidential but not *whose* it is, so any submitter membership would unmask every jurisdiction's restricted cells. The mask therefore repeats the segment-9 test, and the fixture includes restricted rows in multiple jurisdictions.
* **Typed absence:** the mask returns `DECIMAL(38,3)` or `NULL`, never a string sentinel or a fabricated zero.
* **Privilege ordering:** administrators and the owning submitter are evaluated *before* the confidentiality branch, so an entitled reader always sees the true value.
* **Structural density preserved:** the row still exists with all its dimensions intact, so researcher joins and dimensional counts remain correct — only the metric is withheld. The portal surfaces this explicitly, reporting how many values a query had withheld rather than silently returning blanks.

That structural visibility is an information release. Published totals, related
breakdowns and row presence can reconstruct masked values. Community synthetic
tests are invited through the [reconstruction challenge](../SECURITY.md#statistical-reconstruction-challenge).
Restrict or remove the Researcher role if existence disclosure makes inference
trivial; public totals also require an approved disclosure method.

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
* **Protected policy deployment:** the executor creates immutable content-addressed functions, verifies their definitions, changes bindings without dropping protection, and verifies binding metadata. Unexpected errors abort. Existing incompatible tables require explicit migration; success is not inferred from skipped errors.
* **Stable execution, explicit ownership:** the job's `run_as` is a configured service principal. This does not transfer existing objects automatically; table/function ownership, Azure rights and GitHub administration remain explicit handover decisions.

> **Deployment prerequisite:** the pipeline Service Principal **must** be a member of `sg-sovereignshield-admin`. Ownership does not exempt a principal from a row filter. The SCD2 engine reads the target table to locate records to expire; if RLS hid those rows, the merge would treat every row as new — silently duplicating history and never closing prior versions. This fails without raising an error.

---

## 5. The atomic batch quarantine engine

BIS statistical submissions are accepted or rejected **as an indivisible unit**. Partial publication is not merely undesirable — it is incoherent: the aggregates that reconcile depend on the components that did not, so publishing the passing subset would emit an internally contradictory dataset.

`SDMxRuleValidator` parses the reviewed workbook and evaluates its implemented
within-dataset rules. The interpreter is code and requires independent semantic
review; changing metadata requires review and regression tests. Input contracts
enforce one country/period/aggregation per full submission. Checks 22-27 are
explicitly unsupported, and missing breakdowns are reported as not evaluated.

| Batch outcome | `QUALITY_STATUS` | `BATCH_STATUS` | `FAILED_RULE_ID` |
| --- | --- | --- | --- |
| **Any** record in the reporting-period batch fails | `FAIL` on **every** row | `QUARANTINE` | Per-observation violation; batch union is separate `BATCH_FAILED_RULE_ID` |
| All records pass | `PASS` | `PUBLISHED` | `NULL` |

The validator is the single source of truth for these three columns; no downstream stage overrides them. There is no manual approval step and no intermediate `UNDER_REVIEW` state.

**Failure isolation is per-jurisdiction.** Grouping on `(reporting_country, date_scope)` means a Canadian reconciliation break quarantines Canada's period and nothing else — the US and UK submissions in the same run publish normally. Sovereign failure domains do not cascade.

### Prior-state preservation

The critical property: **a rejected revision never degrades what consumers can already see.** The merge engine splits the incoming batch on `BATCH_STATUS` before touching the target.

| Incoming | Prior active record | Row written | Visible in `v_agg_sdmx_published` |
| --- | --- | --- | --- |
| `PUBLISHED` (changed) | Expired → `IS_CURRENT = false` | `IS_CURRENT = true` | The new value |
| New `PUBLISHED` filing with identical values | Previous current scope closed | New submission identity retained | Same values, new accepted filing |
| Replay of the same submission | Untouched | None | Unchanged |
| `QUARANTINE` | **Untouched — remains `IS_CURRENT = true`** | Audit row, `IS_CURRENT = false`, `VALID_TO = VALID_FROM` | **The last valid value** |

Quarantined rows are excluded from both the expire-merge *and* the scoped logical delete. A failed resubmission therefore degrades to **stale data, never to missing data** — the rejection is fully recorded for audit and diagnosis, while the published series continues uninterrupted.

Replay is keyed by immutable submission identity and payload validation. Reusing
an ID with altered bytes/content is refused; a genuinely new identical filing is retained.

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

The [shared submission contract](../src/submission_history.py) and
[Spark adapter](../src/spark_submission_history.py) stage expiry and inserts into
**one Delta MERGE per submission**. Natural observation identity is
`(TIME_SERIES_CODE, DATE, AGG_CODE)`; `RECORD_ID` also includes `SUBMISSION_ID`.

1. Validate nonempty full-snapshot scope, duplicate keys, source digest and message identity.
2. For a newer accepted filing, close every current row in the exact
    country/period/aggregation scope, including keys absent from a smaller replacement.
3. Insert the complete accepted snapshot with `IS_CURRENT=true` and `VALID_TO=NULL`.
    Rejected and older accepted arrivals remain audit-only with closed intervals.
4. Commit staged operations once. Macro history and the educational ledger remain
    separate transactions; replay-safe ledger IDs support repair, not distributed atomicity.

`SUBMITTED_AT` is sender-reported; `RECEIVED_AT` is processing time. Production
requires a trusted sequence/receipt contract. The job is single-writer, and a local
file lock coordinates cooperating local writers only. See the
[migration and concurrency boundaries](RELEASE_EVIDENCE.md#submission-contract).

---

## 7. The public data portal and SDMx REST gateway

The locks above are only interesting if something actually exercises them from outside the workspace. `src/api_gateway.py` is a single FastAPI process that serves both the REST API under `/api/v1` and a BIS-style filter dashboard at `/`, deployed as a Databricks App.

**The gateway selects the SQL identity and lifecycle query; UC enforces row/value entitlement.** The gateway remains trusted because it handles bearer tokens and elevated results. Standard feeds are current/published-only; audit CSV preserves rejected filings separately. See [current release evidence](RELEASE_EVIDENCE.md) for migration and verification limits.

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
| `GET /api/v1/export/audit-csv` | Submission-aware export; quarantine requires submitter/admin entitlement |
| `GET /api/v1/whoami` | The security context the portal banner renders |
| `GET /api/v1/health` | Catalog connectivity, backend mode, and structure availability |
| `GET /api/v1/auth-diagnostics` | Presence-only Easy Auth diagnostics; never returns token or claim values |

Every caller-supplied value is bound as a query parameter, and code values are additionally constrained to `[A-Za-z0-9_]{1,12}` before they reach the warehouse — parameter binding already prevents injection, the pattern check keeps malformed input from being blamed on the metastore.

**Analyst reconciliation.** `lifecycle=published|all|quarantine` distinguishes
current accepted data from rejected arrivals. The Analyst View is the submitter
workflow for checking that the international organization's actual latest filing
state matches the analyst's expected submission. IDs, submitted/received timestamps,
values and failure feedback support this check. The portal does not replace an
authorized full-history query or a transport receipt service.

### SDMx 3.0 serialization

`src/sdmx_ml_exporter.py` replaces the flat CSV export with the formats a statistical portal is expected to speak, all reported against the BIS Data Portal dataflow `BIS:WS_LBS_D_PUB(1.0)`.

* **SDMX-ML 3.0.** SDMX 3.0.0 **removed** the Generic Data format, so `StructureSpecificData` is the only XML data message the standard still defines; the `output_type` argument exists for forward compatibility and rejects anything else rather than silently emitting a 2.1-era payload. Serialization runs through `pysdmx`, which writes against the published schemas, and the emitted document is round-tripped through the reader before it is returned — an invalid message is caught here, not by the receiving institution.
* **Pinned structure.** Normal serialization uses the reviewed local BIS LBS 1.0 component/codelist snapshot and pysdmx 1.18.0. It does not silently fall back to an unvalidated writer or depend on a registry request for each export. `Test=true` identifies synthetic messages, not standards accreditation.
* **SDMX-JSON 2.0.0** for browsers and **SDMX-CSV 2.0.0** for tabular consumers — the latter carrying the standard's `STRUCTURE,STRUCTURE_ID,ACTION` prefix so a file is self-describing rather than depending on an out-of-band agreement about column order.

A masked observation is serialized as an **absent** value, never as zero. Under SDMx semantics those mean entirely different things, and conflating them would turn a confidentiality control into a data-quality defect.

### Deploying the portal

```bash
python sh/activate_databricks_app.py --host <workspace-url> --app-name sovereignshield-portal --target dev --resume
```

Use [Stage 6 of the operations runbook](AUTOMATION_RUNBOOK.md#resume-or-bound-a-run)
for the complete identity-and-activation sequence. Stage 3 uploads the source;
Stage 6 resolves its workspace path from the selected bundle even before an App
has a default path. Bounded waits verify the exact deployment; resumes do not
submit a duplicate snapshot. App dependencies exclude ingestion/Spark components.

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

The public proxy identity has explicit public entitlement. The gateway handles
that credential and signed-in bearer tokens/results, selects lifecycle filters,
and remains trusted. UC independently enforces table row/value entitlements.

| Concern | How the deployment handles it |
| --- | --- |
| Credentials | Public proxy credentials use Key Vault references. The Easy Auth SAS is generated transiently, stored as a Container App secret through a Windows-safe quoted handoff, and never written to tracked files or logs. |
| Image build | `az acr build` — built in Azure, so no local Docker daemon and no image pushed from a workstation |
| Container privileges | Runs as an unprivileged UID with serving modules, decimal/contract helpers, pinned structure, templates and local CSS. Ingestion, synthetic records and the rulebook workbook are excluded. |
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
