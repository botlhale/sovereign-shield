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
  `admin_lead`, `boc_analyst`, `fed_analyst`, `econ_researcher`.
- The operator has Azure subscription permissions, Databricks account-admin
  rights and permission to grant Entra consent for Container Apps sign-in.
- No password, client secret or token is passed to either orchestration script.

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
| 1 | Terraform foundation with deferred grants/gateway disabled | 8–20 min |
| 2 | Databricks account wiring and persona traversal/warehouse grants | 2–5 min |
| 3 | Validate and deploy the Databricks Asset Bundle | 1–3 min |
| 4 | Run security DDL, SDMx generation, validation and SCD2 pipeline | 8–15 min |
| 5 | Bind table and policy-function grants | 1–3 min |
| 6 | Start the Databricks App and bind its public identity | 2–5 min |
| 7 | Build and deploy Container Apps with anonymous + Entra access | 8–18 min |
| 8 | Verify both portals and optionally configure GitHub | 1–3 min |

First-run duration is normally 30–70 minutes. Regional capacity, RBAC
propagation, cluster start and ACR build queues are the main sources of variance.

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

## Architecture image

The enterprise lifecycle image-generation prompt is in
[image_prompts.md](image_prompts.md#terraform-deployment-lifecycle-prompt).
