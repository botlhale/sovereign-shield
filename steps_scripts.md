# Script Helpers and Isolated Demonstrations

The supported complete lifecycle uses [sovereignshield_up.ps1](sh/sovereignshield_up.ps1)
and [sovereignshield_down.ps1](sh/sovereignshield_down.ps1) around Terraform and
Databricks Asset Bundles. See [the operations runbook](docs/AUTOMATION_RUNBOOK.md).
This reference covers focused helpers and the boundaries of legacy imperative
bootstrap scripts; it is not an alternative production acceptance path.

## Information and Ownership Scope

The modeled international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely as educational artifacts illustrating the
calculation of realistic observations. The demo ledger is not an institutional
intake requirement or system deliverable. Domestic granular collection is separate.

Use one owner for each infrastructure resource, grant pair and policy binding.
Do not run imperative create/delete helpers against Terraform-owned resources
without an approved adoption or recovery plan. Existing credentials, account
identities and state must not be replaced solely to resolve a transient wait.

## Supported Entry Point

```powershell
az login --tenant "<tenant-guid>"
az account set --subscription "<subscription-guid>"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force
.\sh\sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>"
```

Existing human users, local configuration, remote state and authorized account/
subscription administration are prerequisites. The wrapper configures workspace
authentication from current Terraform outputs; no separate `pre_auth` is required
before `up`.

## Focused Helpers

| Helper | Responsibility | Boundary |
| --- | --- | --- |
| [pre_auth.ps1](sh/pre_auth.ps1) | Process-scoped authentication for manual operations | Dot-source when its environment must remain in the calling shell; no source credential literals |
| [databricks_account_setup.ps1](sh/databricks_account_setup.ps1) | Account groups, identities, assignments and SQL entitlements | Use exact runtime/proxy application IDs; setup is not continuous Entra synchronization |
| [configure_bundle.py](sh/configure_bundle.py) | Current outputs to target override JSON | Complex cluster object remains structured; do not inject it as a BUNDLE_VAR string |
| [configure_run_as.py](sh/configure_run_as.py) | Deployer use permission on the exact runtime identity | Preserve existing grants; bounded read-back, no role escalation on verification failure |
| [activate_databricks_app.py](sh/activate_databricks_app.py) | Bundle-resolved source and exact-deployment activation | Fresh App may have no default path; resume reconciles pending/latest deployment |
| [container_apps_deploy.ps1](sh/container_apps_deploy.ps1) | Image build, script-owned gateway, vault references and optional Easy Auth | Alternative to Terraform gateway ownership; verified image required before rollout |
| [wait_databricks_run.py](sh/wait_databricks_run.py) | Bounded existing-run completion and task-state reporting | Not a command to regenerate submissions |
| [live_persona_checks.py](sh/live_persona_checks.py) | Temporary synthetic test identities and real persona SQL assertions | Requires authorization, cleanup and a reachable test workspace |
| [kv_spn_remediation.sh](sh/kv_spn_remediation.sh) | Legacy destructive identity/credential remediation | Not routine offboarding; do not delete stable client runtime identities |

Legacy [databricks_create.sh](sh/databricks_create.sh),
[kv_spn_create.sh](sh/kv_spn_create.sh) and
[grp_users_create.sh](sh/grp_users_create.sh) are standalone demonstration helpers.
They do not establish the complete Terraform-owned compute, readiness, review and
ownership contract. Their use needs an isolated approved scope; a legacy script
name is not evidence of a supported fresh production deployment route.

## Recovery Examples

After a Stage 3 identity-use verification failure, preserve earlier stages:

```powershell
.\sh\sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -StartAtStage 3
```

After a Stage 6 activation failure, use the same command with `-StartAtStage 6`.
The helper resolves the selected bundle's workspace source path, assigns public
membership before activation, and creates one snapshot if none exists. An older
running deployment cannot conceal failure of the latest deployment.

After a failed build, the gateway helper can use a verified existing image:

```powershell
.\sh\container_apps_deploy.ps1 `
  -KeyVaultName "<current-vault-name>" `
  -DatabricksHost "<current-workspace-host-without-https>" `
  -WarehouseId "<current-warehouse-id>" `
  -RegistryName "<existing-registry>" `
  -ImageTag "<verified-repository:tag>" `
  -SkipImageBuild `
  -EnableEntraSignIn
```

Use current outputs, not identifiers copied from historical deployment records.
Readiness flags and existing grants must be preserved. Repair ingestion against
archived messages; generator reruns create new filing identities.

## Verification and Handover

The four job tasks apply protected DDL, generate synthetic SDMx, ingest/validate
history and run actual runtime acceptance. Verify both host configurations and
signed-in persona behavior; Stage 8 alone is not a complete human SSO test.

The **Analyst View** compares expected latest filings with actual receiver IDs,
timestamps, values and feedback. Current accepted publication remains distinct
from a later rejected filing. Researcher row presence and public totals can expose
masked values; follow the [open reconstruction challenge](SECURITY.md#statistical-reconstruction-challenge)
and restrict/remove that role where disclosure approval requires it.

Client handover includes approved source transfer, client-owned repository/state/
identities, synthetic staging, production approval and operator acceptance. Remove
provider memberships, sessions/tokens, RBAC, vault/GitHub rights and delegated
ownership; review exports and rotate accessible credentials with consumer refresh.
Keep stable client runtime identities. No three-command checklist guarantees
complete revocation. See [the engagement specification](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md).

## Cost and Teardown

Successful reference provisioning took approximately **75 minutes including
prerequisites**, with **30 minutes for teardown** and **US$10 or less in Azure
charges for deploy/test/teardown**. These are bounded synthetic observations, not
a price guarantee; see [measurement scope](docs/RELEASE_EVIDENCE.md#reference-evaluation-metrics).

Use `sovereignshield_down.ps1 -Mode Workload -WhatIf` before approved destruction.
Pause is not guaranteed zero cost. Backend storage, account records and other
retained artifacts have explicit ownership/retention requirements; workload
cleanup does not prove every tenant identity was removed.

The information/delivery framework is technology-agnostic. Terraform-supported
AWS, GCP, Fabric and open-source implementations need equivalent adapters and
acceptance tests; the legacy imperative helpers do not supply those ports.