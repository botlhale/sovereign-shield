# Release Evidence and Migration

**Scope:** Independent synthetic reference implementation, locally verified in September 2026. This revision has not been applied to Azure. Historical deployment screenshots and saved exports are not evidence that the changed policy, decimal schema, job ownership or CI workflow has run in Unity Catalog.

## Reproducible Methods

**Recorded local result, 15 September 2026:** Python 3.13.14, pandas 3.0.5, pysdmx
1.18.0, delta-rs 1.6.2: **159 passed, 3 skipped** in the stress-enabled suite.
The skips were two live Databricks tests and the Spark benchmark
(`JAVA_GATEWAY_EXITED`). Terraform format/validate and PowerShell syntax checks
passed. Desktop 1440x900 and mobile 390x844 portal checks found no page overflow;
admin presentation was tested with labelled browser fixtures, not live auth.
The eight-page executive brief and sixteen-page whitepaper were proofed with
isolated Chrome; all ten whitepaper figures shared pages with their captions.
The local Markdown checker resolved 245 links and heading anchors.

Use the selected virtual environment and the committed dependency manifests. No Azure credentials are required for these commands:

```powershell
.venv\Scripts\python.exe -m pytest -v tests/ -rs
.venv\Scripts\python.exe -m pytest -v tests/ --stress -rs
.venv\Scripts\python.exe sh/local_demo.py
$env:SOVEREIGNSHIELD_LOCAL_DELTA = "$PWD\.pytest_cache\demo\catalog"
.venv\Scripts\python.exe -m uvicorn api_gateway:app --app-dir src --host 127.0.0.1 --port 8000
```

Unset Databricks connection variables for the local server; a configured warehouse deliberately disables local fallback. Local files are synthetic and are not a security boundary against someone who can read the filesystem. The portal has no local production impersonation switch. Browser persona fixtures test presentation, while API/persona tests exercise the local policy mirror.

| Evidence | Check | What It Does Not Establish |
| --- | --- | --- |
| Failed binding cannot report success; normal deployment never detaches policies | [Policy tests](../tests/test_policy_deployment.py) | Actual UC DDL execution or atomic multi-object policy changes |
| Unknown names/codes, duplicate keys, invalid periods and sender mismatch refused | [Input tests](../tests/test_input_contract.py) | Full provision-agreement or dataflow constraints |
| Three-place decimals survive XML, CSV and JSON; duplicate standard observation keys refused | [Input and wire tests](../tests/test_input_contract.py) | Recovery of precision already lost in historical DOUBLE data |
| Official SDMx-JSON 2.0.0 schema used independently | Pinned schema and `jsonschema.Draft7Validator` | Formal accreditation by a standards owner |
| Real local Delta commits preserve replay identity, shorter replacements, rejection isolation and failure atomicity | [History tests](../tests/test_submission_history.py) | Distributed concurrency, multi-table transactions or cloud throughput |
| Published/quarantine/all views, feedback and separate audit export | [API tests](../tests/test_lifecycle_api.py) | Live Easy Auth, Entra or Databricks persona session acceptance |
| No PR federation; state readiness and destructive-plan checks | [Deployment tests](../tests/test_deployment_boundaries.py) | Live GitHub protection or Terraform apply |

The original binding and input-validation regressions were observed failing before correction. The test suite retains explicit live and stress markers. A skipped gate is not a pass, and a source-contract assertion is not an engine execution test. Record the tested commit with `git rev-parse HEAD` and retain the full command output with each published release; do not substitute an evergreen test-count claim for that evidence.

## Submission Contract

One immutable message ID identifies one nonempty full country/period/aggregation snapshot. A message ID reused with different bytes or validation content is refused. Replaying the same accepted or rejected message does not add rows or a Delta commit. A new message with identical values remains a distinct filing.

An accepted replacement closes all current rows in its exact scope and inserts the complete new snapshot in one table transaction, including retiring keys omitted by a smaller replacement. A rejected replacement inserts closed audit rows only. An older accepted filing arriving after a newer submitted timestamp is retained audit-only. `SUBMITTED_AT` is sender-reported; `RECEIVED_AT` is receiver processing time, not an asserted original transport receipt. Production must define a trusted receipt/sequence contract, clock-skew policy and late-arrival approval process.

`VALID_TO=NULL` denotes an open current interval. Rejected and late audit-only rows have `VALID_TO=VALID_FROM`. The record key includes submission identity and the full observation key. The content hash detects identity reuse; it does not replace the submission ID. Empty replacements and Append/Delete messages require a future explicit scope/action contract and are refused.

The job uses one concurrent run, and cooperating local writers use a file lock. Separate deployments, notebooks and privileged external writers are not coordinated by that job setting. Restrict `MODIFY` to the ingestion identity in an institutional deployment and test conflicts on the actual runtime. Macro and raw-ledger writes are separate transactions; replay-safe ledger IDs enable repair, not distributed atomicity.

## Decimal and Standards Profile

Measures use `DECIMAL(38,3)`. Intake uses decimal half-up rounding; calculations use decimal arithmetic; serializers do not use six-significant-digit `:g` formatting. API observation values are decimal strings or `null`, and standard JSON numbers are emitted by a decimal-aware serializer. This API type change is intentional. Original XML remains the unrounded source evidence.

The synthetic reporting profile is millions of USD (`UNIT_MEASURE=USD`, `UNIT_MULT=6`), end-of-period (`COLLECTION=E`), with `DECIMALS=3` and a frequency-derived `TIME_FORMAT`. `AVAILABILITY=A` describes dissemination availability; it does not override `OBS_CONF` or grant access. Currency denomination is a dimension, not a request to convert amounts. Zero is retained; masking is absence, never zero. SDMx itself does not require all data to have three decimals.

Four checks must not be conflated:

1. Message format: XML validation through pysdmx with validation enabled, and official versioned JSON Schema tests.
2. DSD: required components, names, dimensions, order, supported values and reference-profile types.
3. Domain/provisioning: pinned codelists and the configured sender-country mapping. Complete dataflow/provision-agreement constraints are not implemented.
4. Arithmetic: 21 parsed within-dataset workbook checks. Cross-collection checks 22-27 are reported as unsupported. Missing breakdowns are explicitly not evaluated. Independent review of rule placeholder and residual semantics remains necessary.

The structure snapshot is an extracted component/code contract, not a full registry. Refresh it deliberately using [the refresh helper](../sh/refresh_lbs_contract.py), inspect its diff and rerun tests. Runtime reads do not fetch an unreviewed `latest` structure. Source URL, response digest and retrieval time are recorded in the snapshot. Historical demo exports predate this metadata profile.

## Mandatory Migration Gate

**Do not deploy this release over the old DOUBLE history as a routine update.** The policy executor refuses incompatible existing schemas before changing bindings; the Spark writer also refuses missing or legacy tables. This session does not authorize or perform a cloud migration.

For a retained environment, the platform owner must approve and rehearse a migration:

1. Inventory existing tables, policies, grants, job IDs, bundle state path, active writers, archive coverage and backups. Verify an independent recovery path and restrict consumers during cutover.
2. Create new protected decimal/history tables under temporary names, with policies inline before any load or grants. Preserve old protected tables and their Delta versions. Never detach protections to change a bound function.
3. Replay original immutable arrivals into the new contract in approved order. Legacy row hashes alone cannot recover submission identity; where source evidence is missing, retain an explicitly labelled legacy archive rather than inventing IDs or receipt times. Report decimal conversion differences and preserve original values.
4. Validate counts, current-key uniqueness, accepted/rejected separation, temporal intervals, three-place values, and the complete live persona matrix. Verify new function definitions and all bindings from UC metadata.
5. Reconcile the existing job/app with the shared bundle state path and stable `run_as` identity. Bind/import existing resources using the CLI-supported procedure for the installed version; do not deploy a second ingestion job from a new state path. Transfer table/function ownership only through reviewed administrative changes.
6. Switch consumers through a reviewed cutover, test rollback, then restore approved grants. Retire old protected resources only under the retention decision. Do not claim transactionality across this multi-object migration.

For a disposable synthetic environment, an approved teardown and fresh bootstrap is simpler, but it destroys workload data. The existing `down` confirmation is still required. No destruction was run for this revision.

## CI, Ownership and Cost

PR and push workflows run credential-free verification. Cloud planning is privileged, not a read-only PR identity; it runs only for a manually selected operation on reviewed `main`, behind required independent reviewers. CI verifies the environment gate and refuses unbootstrapped state. It does not currently rebuild the script-owned Container Apps host; the `up` command owns that complete lifecycle. Do not label bundle-only promotion a complete two-host rollout.

The old PR federation credential is removed by configuration, but it remains live until an authorized apply removes it. Live GitHub reviewer/status-check settings were not changed. Required status checks and an independent reviewer must be configured before promotion; a sole contributor cannot self-approve an independent gate.

Terraform owns grants, including schema `EXECUTE`; the bundle sets `SOVEREIGNSHIELD_SKIP_GRANTS=1`. The script-only grants file is the alternative owner, not a concurrent one. Schema `EXECUTE` is suitable only while these are dedicated policy schemas; placing unrelated privileged functions there requires a grants redesign. Singular `databricks_grant` is authoritative for its principal/securable pair, not universally additive.

Company-controlled service principals and a shared bundle workspace path support continuity. Runtime identity, resource ownership, repository administration and human group membership are distinct controls. Full offboarding includes Entra/Databricks groups, tokens/sessions, Azure RBAC, vault rights, GitHub rights, delegated ownership and emergency access. Rotate only credentials the departing person could access, refresh consumers and test recovery; routine group removal alone is not complete revocation.

`up` preserves state-derived readiness, uses unique temporary plans, checks for destructive changes and holds a checkout-level lifecycle lock. Cross-machine orchestration still requires one authorized controller; Terraform's state lock covers individual Terraform operations, not the entire run. Pause requests scale-to-zero eligibility, not guaranteed shutdown or zero cost.

Default ingestion remains single-node, no Photon. Terraform supplies the complete job-cluster specification and policy ID; larger compute needs `-ApproveComputeScale`. Cloud estimates should parameterize region, VM/DBU runtime, warehouse size/concurrency, app replicas, storage, logs, network egress and retained resources. Obtain estimates from the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/) and reconcile them with tagged Azure Cost Management and job-run metrics. No savings percentage, production throughput or cloud cost benchmark is claimed.

## Release Limitations

RLS/DDM is entitlement enforcement, not statistical disclosure control. Synthetic public totals can reconstruct restricted components. An originating authority must approve secondary suppression, perturbation or another suitable control before release of real confidential statistics. Logical segregation is not country-level physical residency. A gateway compromise can misuse tokens and returned data. Downloads cannot revoke themselves. Infrastructure administrators remain privileged. This reference implementation is production-isolated, not air-gapped.

Third-party redistribution and exact copyright assignment need independent provenance. Consultancy clearance reported by the author is not presented as certification of this specific publication. See [reference provenance](reference_standards/README.md), [NOTICE](../NOTICE), and the personal-capacity notice in the whitepaper.