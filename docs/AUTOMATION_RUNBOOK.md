# SovereignShield One-Command Operations

The orchestration scripts wrap the existing Terraform runbook. They do not
replace Terraform, Databricks Asset Bundles or the stage-specific scripts; they
execute those tools in the required order and stop on the first failed gate.

For a resource-by-resource explanation of both Azure resource groups, the
Databricks account layer, creation ownership, reuse behavior, cost relevance,
and teardown ownership, see the
[Systems Architect Resource Provenance Guide](RESOURCE_PROVENANCE.md).

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

| Stage | Action | Typical evaluation time |
| ---: | --- | ---: |
| 0 | Validate tools, config, Azure session, providers, persona users and offline tests | 2–5 min |
| 1 | State-aware foundation; preserve established readiness and gateway ownership; guard the plan | Historical: 8–20 min |
| 2 | Databricks account wiring, persona SQL entitlements and traversal/warehouse grants | 2–5 min |
| 3 | Validate and deploy the Databricks Asset Bundle | 1–3 min |
| 4 | Run security DDL, SDMx generation, validation and SCD2 pipeline | 8–15 min |
| 5 | Bind Terraform table grants; schema EXECUTE is also Terraform-owned | Historical: 1–3 min |
| 6 | Start the Databricks App and bind its public identity | 2–5 min |
| 7 | Build and deploy Container Apps with anonymous + Entra access | 8–18 min |
| 8 | Verify both portals, persona SQL entitlements, 13-row anonymous fixture, Easy Auth/token store, and optionally configure GitHub | 1–3 min |

The earlier deployment's planning range was 30–70 minutes, not a measured guarantee for this revision. Regional capacity, RBAC
propagation, cluster start and ACR build queues are the main sources of variance.
The repository `.dockerignore` restricts the ACR upload to the portal runtime
files; local environments, Terraform providers, data, documentation and demo
media are never sent as image-build context.

The runtime allowlist now includes the extracted structure/code contract and
compiled local CSS, but not the BIS PDFs or workbook. Rebuild CSS with
`.venv\Scripts\python.exe sh/build_portal_css.py` after template style changes.

### Resume or bound a run

Every stage uses idempotent underlying operations. Resume at a failed stage:

```powershell
./sh/sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -StartAtStage 4
```

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
