# Live Deployment: 15 September 2026

## Status

The synthetic workload was bootstrapped in Canada Central from an empty workload
resource group and empty Terraform state. The state backend and existing account
identities were retained. The deployment used commit `0f82b81` plus the recovery
fixes in the working tree, not an unmodified deployment of that commit.

The user authorized a rebuild if needed and a $50 spending ceiling. No existing
workload data needed deletion. The user subsequently confirmed "testing complete"
and authorized the post-test teardown. The teardown preview found no active job
runs and all job clusters terminated. Teardown completed successfully, with
independent cleanup verification at **2026-09-16 00:45 UTC** (15 September locally).
Both cloud portals are now inactive; the identifiers below describe the removed
evaluation deployment.

## Live Resources

| Resource | Identifier |
| --- | --- |
| Workload group | `rg-sovereignshield` |
| Workspace | `7405613190562799`, Canada Central |
| SQL warehouse | `0dd3293934137b7b`, 2X-Small, one cluster, 10-minute auto-stop |
| Pipeline job | `434609918006671` |
| Successful repaired run | [504168656605624](https://adb-7405613190562799.19.azuredatabricks.net/jobs/434609918006671/runs/504168656605624) |
| Runtime service-principal app ID | `b3143e4b-cd26-44b3-ae36-9bc7a2e6371f` |
| Bundle source path | `/Workspace/SovereignShield/dev` |
| Databricks App | [Signed-in portal](https://sovereignshield-portal-7405613190562799.19.azure.databricksapps.com) |
| Container Apps | [Public and Entra sign-in portal](https://ca-sovereignshield-portal.delightfulcliff-e8fbf897.canadacentral.azurecontainerapps.io) |
| Registry / token storage | `acrsovereignshield16555` / `stsovereignshieldauth539` |
| Key Vault | `kv-sovereignshield-26171` |

The application directory's live ACL contains the platform admin group and
inherited workspace administrators, not a broad users write grant. The dev target
uses bundle production-mode semantics for a stable application-owned path; it
still denotes synthetic evaluation, not production data.

## Verified Outcomes

The final local stress-enabled suite passed **184 tests**, with three explicit
skips in that invocation: two opt-in live pytest cases and the local Spark
throughput benchmark (no working JVM). Both live pytest cases were run and passed
separately against this workspace. Actual Spark/UC correctness was exercised by
the deployed acceptance task, not substituted for the unrun throughput benchmark.
Terraform fmt/validate, PowerShell parser/regression checks, editor diagnostics,
249 local documentation links and the final no-drift Terraform plan passed.

The first run failed in policy metadata verification. A subsequent run passed
policy setup and generation but failed the DataFrame MERGE. Repair reran only
ingestion and the downstream acceptance task. The final run result is SUCCESS.
Successful task IDs are `764648104119498` (policies), `742184731086163`
(generation), `849518661408903` (ingestion), and `868796956958866` (acceptance).

[The live runtime task](../src/live_runtime_checks.py) verified actual UC policy
definitions/bindings and DECIMAL(38,3) storage, replayed arrivals without macro or
micro row growth, and preserved 22 current observations. An isolated protected
test table verified one-commit accepted replacement, retirement of omitted keys
only in the correct scope, rejection isolation, identical new filing retention,
late-older handling, identity-reuse refusal, and unique record/current keys. The
temporary table was dropped afterward. These bounded cases do not prove
distributed concurrency, production throughput or multi-table atomicity.

[The live persona harness](../sh/live_persona_checks.py) used real temporary
Databricks principals with one-hour OAuth secrets. It did not modify human users'
memberships or enable PATs. All seven test principals and their secrets were removed.

| Persona | Rows, Current Plus Allowed Quarantine | Masked Values |
| --- | ---: | ---: |
| Public | 13 | 0 |
| Researcher | 22 | 9 |
| CA submitter | 18 | 0 |
| US submitter | 21 | 0 |
| Administrator | 44 | 0 |
| CA submitter plus researcher | 26 | 8 |
| Unaffiliated, with object reachability but no persona | 0 | 0 |

Public live XML, JSON, SDMx-CSV and audit CSV each contained 13 observations.
XML was read with pysdmx validation enabled; JSON was checked against the official
2.0.0 schema. CSV measures retained three decimal places. Cache directives included
private and no-store; the platform reordered their presentation. Anonymous
quarantine requests returned 403.

An additional temporary CA OAuth identity passed API identity resolution,
quarantine-only search (four rows with submission and failure feedback), an
18-row audit export, and refusal of a standard SDMx export in audit mode. It and
its secret were removed. The repository's two existing live pytest checks were
also run successfully; the public check was rerun after fixing auth-mode selection.

Public browser checks at 1440x900 and 390x844 verified 13 displayed rows,
three-place values, no page overflow or external JavaScript, a CA filter result
of three rows, and reset to 13. Orchestration Stage 8 passed. The user subsequently
reported testing complete; individual human sign-in results were not supplied.
Temporary-principal API checks are not a substitute for a recorded human sign-in
acceptance matrix.

At handover, the final public container revision was `ca-sovereignshield-portal--0000004`, using
`sovereignshield-portal:live-20260915-auth`. Its provisioning state was Succeeded;
the Databricks App reported RUNNING. The final public search returned HTTP 200 with
13 rows. No active job runs or temporary test service principals remained at handover.

## Recovery Fixes

- Native command progress remains visible through callers' Out-Null.
- Python reads Terraform state/plan JSON directly, avoiding unreliable PowerShell stdin piping.
- Cluster-policy numeric constraints retain numeric JSON types, including zero workers.
- Complex bundle variables use target-specific override JSON, not environment strings.
- Terraform's exact application IDs are used; duplicate display names are refused.
- The deployer receives explicit service-principal use permission; existing grants are preserved and read-back uses the updated ETag.
- Policy verification supports the actual runtime's qualified function names and target/using-column metadata while rejecting missing or wrong bindings.
- A single native SQL MERGE over a temporary view avoids the observed Spark Connect self-reference alias failure.
- The Dockerfile includes decimal, structure and stylesheet runtime files.
- Failed ACR builds/pushes or missing image digests stop gateway deployment; verified images can be reused with SkipImageBuild and ImageTag.
- Container Apps uses explicit managed-identity registry access and registry-scoped AcrPull, with one evaluation replica maximum.
- The SQL client explicitly selects Azure client-secret authentication for the Entra proxy and OAuth M2M for App-managed credentials.

The approved demo UPNs are now submitter_ca and submitter_us at
13668754CANADAINC.onmicrosoft.com. Their Entra object IDs and credentials were
preserved; no password reset was performed. Admin/researcher logins are unchanged.

## Cost and Teardown Boundary

All three job clusters were verified TERMINATED after the repaired run. Ingestion
used Standard_DS3_v2, zero workers and no Photon. SQL auto-stops after ten idle
minutes; Container Apps is capped at one replica. SQL Serverless's engine settings
are separate from ingestion's Photon setting.

Azure Cost Management returned HTTP 429 during deployment. The billed total could
not be verified and is not reported as below $50; billing also lags resource use.
The workload is now removed, but the retained state backend can incur storage
costs. No hard real-time billing cap or zero-total-cost claim is made.

## Teardown Results

After the user's testing-complete confirmation, the scoped teardown was previewed
with `-WhatIf`, then executed with `-Mode Workload -ConfirmWorkloadDestruction
-Confirm:$false`. The existing script completed without a teardown repair.

- Removed the synthetic tables/view, policy functions, bundle job/App and uploaded bundle directory.
- Deleted the Container App, its environment, registry and token-store storage account.
- Terraform reported **55 resources destroyed**, including the SQL warehouse, catalog/schemas/volume, workspace, data storage, and Terraform-owned Entra applications, groups and credentials.
- Deleted the orphaned Log Analytics workspace after Terraform destruction.
- Independently verified `terraform state list` returned zero entries and `rg-sovereignshield` contained zero Azure resources.
- Verified the managed resource group `databricks-rg-rg-sovereignshield` no longer exists. No workload compute remains.
- Verified the remote-state blob remains accessible in `rg-sovereignshield-tfstate` / `stsovshieldtfstate`; its final size was 1,032 bytes.
- Verified the five persona groups, four demo users and two deployment/proxy service-principal records remain in the Databricks account directory. These are separate from the Terraform-owned Entra objects that were removed.
- Verified Key Vault `kv-sovereignshield-26171` is soft-deleted with purge protection and scheduled purge on 15 December 2026. No purge was attempted.

The workload resource group itself is retained empty. Script-owned Entra sign-in
registrations and older account artifacts are outside this scoped workload
teardown; an empty workload group is not a claim that the tenant has no identities
or credentials. Source changes, local synthetic fixtures and the state backend
were not deleted.