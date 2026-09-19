# SovereignShield One-Command Operations

The orchestration scripts wrap the existing Terraform runbook. They do not
replace Terraform, Databricks Asset Bundles or the stage-specific scripts; they
execute those tools in the required order and stop on the first failed gate.

For a resource-by-resource explanation of both Azure resource groups, the
Databricks account layer, creation ownership, reuse behavior, cost relevance,
and teardown ownership, see the
[Systems Architect Resource Provenance Guide](RESOURCE_PROVENANCE.md).

**Scope:** the international exchange contract is SDMx files only. Synthetic bank
micro-transactions are educational calculation fixtures; their demo ledger is not
an institutional intake requirement or system deliverable. Production adaptation
must replace demo generation, accept disclosure controls and establish client
ownership under [Nature of Engagement and Handover](ENTERPRISE_ONBOARDING_PLAYBOOK.md).

## Assumptions

Before setup:

- `az login` is active in the target subscription.
- `terraform/terraform.tfvars` and `terraform/backend.hcl` exist and are complete.
- The remote Terraform state backend already exists.
- The four persona users already exist in Entra ID:
  `admin_lead`, `submitter_ca`, `submitter_us`, `econ_researcher`.
- The operator has Azure subscription permissions, Databricks account-admin
  rights and permission to grant Entra consent for Container Apps sign-in.
- No password, client secret or token is passed to either orchestration script.

Existing deployments must migrate any earlier demo usernames and display names
in both Entra ID and Databricks before running preflight with the neutral names.
Changing repository defaults neither renames nor revokes existing accounts.
Keep the `sg-sovereignshield-submitter-ca` and `sg-sovereignshield-submitter-us`
policy groups unchanged and review their memberships during migration.

**Release migration gate:** existing DOUBLE history and per-user bundle paths must
follow [the explicit migration procedure](RELEASE_EVIDENCE.md#mandatory-migration-gate).
The [live evaluation](LIVE_DEPLOYMENT_2026_09_15.md) used an empty workload. Do not run `up` expecting it to
convert historical tables or adopt an existing job from another bundle path.

`-DeploymentMode Auto` inspects Terraform state. Fresh/partial bootstrap preserves
any ready grants; steady-state never resets them. `-DeploymentMode SteadyState`
refuses incomplete bootstrap. A checkout-level lock prevents overlapping `up`/`down`
operations; one authorized controller is still required across machines. Unique
temporary plans are inspected for destructive changes before apply. The obsolete
PR federation credential is the only permitted automatic deletion.

The bundle consumes `ingestion_job_cluster` and `cicd_client_id` outputs for governed
compute and stable `run_as`. Raising worker counts or enabling Photon requires
`-ApproveComputeScale`; defaults remain single-node and no Photon.

Complex compute variables are written to the ignored target-specific bundle
override JSON; the CLI rejects complex BUNDLE_VAR environment values. The source
directory is `/Workspace/SovereignShield/<target>`, restricted to the platform
admin group and workspace administrators. Production-mode bundle semantics permit
this stable non-personal path; the dev target still runs synthetic data only.

After a failed ACR push, deployment stops. Resume from a verified image with
`-RegistryName <existing-registry> -ImageTag <verified-tag> -SkipImageBuild`.
Use job repair for failed data tasks; do not regenerate completed arrivals solely
to repair ingestion.

## Complete setup

```powershell
./sh/sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>"
```

The default run executes:

| Stage | Action |
| ---: | --- |
| 0 | Validate tools, config, Azure session, providers, persona users and offline tests |
| 1 | State-aware foundation; preserve established readiness and gateway ownership; guard the plan |
| 2 | Databricks account wiring, persona SQL entitlements and traversal/warehouse grants |
| 3 | Verify runtime-identity use permission, validate and deploy the Databricks Asset Bundle |
| 4 | Run security DDL, synthetic SDMx generation, validation/SCD2 ingestion and live runtime acceptance |
| 5 | Bind Terraform table grants; schema EXECUTE is also Terraform-owned |
| 6 | Bind the managed public identity, resolve bundle source, activate one snapshot and verify its deployment |
| 7 | Build and deploy Container Apps with anonymous and Entra access |
| 8 | Check App status, persona SQL entitlements, 13-row public fixture and Easy Auth; optionally configure GitHub |

The successful reference evaluation measured approximately **75 minutes to bring
up the entire project, including prerequisite setup**, and **30 minutes for
teardown**. Deployment, testing and teardown incurred **US$10 or less in Azure
charges**. These are observed synthetic-workload results, not stage SLAs or a
guaranteed cost ceiling. Regional capacity, RBAC propagation, runtime, storage,
warehouse activity and retained resources affect each run. See
[measurement provenance and limits](RELEASE_EVIDENCE.md#reference-evaluation-metrics).
The repository `.dockerignore` restricts the ACR upload to the portal runtime
files; local environments, Terraform providers, data, documentation and demo
media are never sent as image-build context.

The runtime allowlist now includes the extracted structure/code contract and
compiled local CSS, but not the BIS PDFs or workbook. Rebuild CSS with
`.venv\Scripts\python.exe sh/build_portal_css.py` after template style changes.

### Resume or bound a run

Resume at the failed stage after identifying which operation completed. Resource
convergence and same-message replay are idempotent; rerunning the synthetic
generator creates new submission identities and is not equivalent to replay:

```powershell
./sh/sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -StartAtStage 4
```

For a Stage 3 runtime identity use-role verification failure, keep the completed
foundation and account setup. A successful grant can become visible after the
initial verification read. The helper retries read-back for up to two minutes
using the returned ETag, without repeating the permission update. It still
requires the exact deployer and `roles/servicePrincipal.user` grant; manager
permissions alone do not qualify. Authorization errors and an unverified grant
after the deadline stop the deployment.

No teardown is needed for this failure. With the existing Azure login and
Terraform configuration, resume stages 3-8:

```powershell
./sh/sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -StartAtStage 3
```

This reads the current Terraform outputs and skips stages 0-2. Add
`-StopAfterStage 3` to validate and deploy only the bundle before continuing.

For an app activation timeout or a missing default source path on a new App,
preserve completed data stages and resume at 6:

```powershell
./sh/sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -StartAtStage 6 `
  -AppTimeoutMinutes 20
```

Stage 6 assigns the managed app identity to the public group before activation.
It resolves `source_code_path` from `databricks bundle validate` for the selected
target. A newly created App can have no `default_source_code_path` until its
first deployment, even though Stage 3 already uploaded the source. An absent
App default is not a reason to tear down or repeat Stage 3. The resolved bundle
resource must match the requested App and contain an absolute workspace path;
resolution failures stop before compute is started.

A fresh run submits one snapshot. A resume waits for the existing pending or
latest deployment from the app's configured bundle source path, without submitting
another snapshot. If no deployment exists yet, it creates one. Success requires
that exact deployment to be successful and active, app compute to be active, the
app to be running, and no replacement deployment to be pending. An older running
app cannot conceal a failed latest deployment.

`-AppTimeoutMinutes` accepts 1-60 minutes (default 20) for each compute-start or
deployment wait. A timed-out wait checks the same deployment once more; it only
recovers if the service reports success. Otherwise the script stops and prints
the deployment ID. Failed or cancelled deployments remain failures. Inspect app
logs and repair the source before deliberately deploying again; timeout recovery
is not a source-update operation. The manual VS Code task
`SovereignShield: resume app and gateway` runs stages 6-8 using current Terraform
outputs instead of a stored workspace URL.
The [18 September recovery record](LIVE_DEPLOYMENT_2026_09_18.md) documents the
successful live resume and its verification limits.

Run preflight only:

```powershell
./sh/sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -StopAfterStage 0
```

Use `-SkipTests` only when the same commit has already passed the offline suite.

### Optional GitHub configuration

```powershell
./sh/sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -ConfigureGitHub `
  -GitHubRepository "<owner/repository>" `
  -GitHubReviewers "<reviewer>"
```

This requires an authenticated GitHub CLI session with repository-admin rights.
The runtime deployment does not depend on GitHub configuration.

## Pause

Pause compute while retaining data, identities and infrastructure:

```powershell
./sh/sovereignshield_down.ps1 -Mode Pause
```

This stops the Databricks App and sets the Container App minimum replicas to
zero. The SQL warehouse and job cluster retain their existing auto-stop behavior.
Zero minimum replicas does not force immediate shutdown: traffic can keep replicas
running. Storage, logs, identity artifacts and other retained resources can still
cost money. Verify tagged actual usage rather than calling Pause zero-cost.

## Workload teardown

Preview the complete ordered teardown:

```powershell
./sh/sovereignshield_down.ps1 -Mode Workload -WhatIf
```

Execute it:

```powershell
./sh/sovereignshield_down.ps1 `
  -Mode Workload `
  -ConfirmWorkloadDestruction
```

The script performs these operations in order:

1. Capture workspace authentication before Key Vault or workspace deletion.
2. Discover and drop live views/tables before policy functions across every
  project schema, rather than relying on fixed object locations.
3. Destroy Databricks bundle resources.
4. Disable and delete the Container Apps gateway through its owning path.
5. Destroy the remaining Terraform-managed workload directly without an
  intermediate apply that could recreate resources after a partial failure.
6. Remove any orphaned Databricks diagnostic Log Analytics workspace.
7. Fail if any Azure workload resource or Terraform state entry remains.
8. Report the resources intentionally preserved.

The default workload teardown preserves:

- the remote Terraform state resource group, account and container;
- Databricks account-level users, groups and service principals; and
- the purge-protected Key Vault tombstone until Azure retention expires.

These resources make rebuilding reliable and do not run compute. Human users are
never deleted by the orchestration script.
Script-created Entra application registrations, credentials and token-store grants
need a separate identity inventory; an empty Azure resource group does not prove
that every identity artifact was removed.

## Safety boundaries

- Workload teardown requires `-ConfirmWorkloadDestruction`.
- `-WhatIf` performs discovery and state inspection but no deletion.
- Re-running after a partial destroy is supported; absent workspaces, catalogs,
  schemas and gateways are treated as already complete.
- Do not interrupt `terraform destroy` or Container Apps environment deletion.
- Copy required submission files before teardown; the managed volume is deleted.
- The scripts do not bootstrap the Terraform backend, create human users, handle
  passwords or remove account-level identities.
- Run either the script-managed or Terraform-managed Container Apps path, not both.

Resource ownership and retention boundaries are detailed in the
[Resource Provenance Guide](RESOURCE_PROVENANCE.md).
