# SovereignShield Resource Provenance Guide

This guide explains every major resource created by the Terraform deployment,
why it exists, which step creates it, what happens when it already exists, and
which tool removes it. It is written for platform owners, systems architects,
security reviewers, and operators reading the Azure and Databricks consoles.

## The Short Operating Sequence

The one-command path assumes the remote Terraform backend, local configuration,
Python environment, and four human Entra users already exist.

```powershell
# 1. Establish the operator identity and subscription.
az login
az account set --subscription "<subscription-id>"

# 2. Provision or converge the complete workload.
powershell.exe -ExecutionPolicy Bypass -File .\sh\sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>"
```

No project authentication script is required before the wrapper. It validates
the active Azure CLI session and configures the Databricks CLI to use Azure CLI
authentication after the workspace URL is available. For manual commands after
Stage 1, `sh/pre_auth.ps1` is optional: dot-source it to discover the current
workspace URL from Key Vault and select either the stored quickstart service
principal or the active Azure CLI identity. It sets process-scoped environment
variables without writing credential values to a file.

## Ownership Boundaries

| Boundary | Created by | Operator expectation |
| --- | --- | --- |
| `rg-sovereignshield` | Terraform, or adopted when `create_resource_group=false` | User-owned workload resources. Terraform and the stage scripts manage these objects. |
| `databricks-rg-rg-sovereignshield` | Azure Databricks while creating `dbw-sovshield` | Databricks-managed internals. Inspect for diagnosis, but do not edit or deploy into it. |
| `rg-sovereignshield-tfstate` | One-time Azure CLI bootstrap | Remote state backend. It intentionally outlives workload teardown. |
| Databricks account | `databricks_account_setup.ps1` | Account groups, users, service principals, memberships, and workspace assignment. These are not Azure resources. |
| Unity Catalog | Terraform plus Asset Bundle pipeline | Terraform owns catalog/schema/grants; SQL owns tables, views, filters, and masks. |

## Why Two Azure Resource Groups Appear

Terraform creates the `dbw-sovshield` workspace in `rg-sovereignshield`. Azure
Databricks then creates and controls `databricks-rg-rg-sovereignshield`. The
second group is not a duplicate deployment. It is the workspace's managed
network, identity, and storage substrate and is marked **Managed by
dbw-sovshield** in Azure.

Deleting the workspace should delete the managed group. The teardown script
also detects the diagnostic Log Analytics workspace Azure can occasionally
orphan after workspace deletion and refuses to report success while workload
resources or Terraform state remain.

## Stage-by-Stage Provenance

| Stage | Command owner | What is created or changed | Existing-resource behavior |
| ---: | --- | --- | --- |
| 0 | `sovereignshield_up.ps1` | Validates tools, config, Azure login, providers, persona users, and tests | Read-only except idempotent provider registration |
| 1 | Terraform | Identity, Key Vault, Databricks workspace, UC storage/connector, catalog, schemas, volume, SQL warehouse, cluster policy | Terraform converges state; the workload resource group can be created or adopted |
| 2 | `databricks_account_setup.ps1`, then Terraform | Databricks account SCIM mirrors, memberships, workspace assignments, catalog/schema/warehouse grants | Lists before creating; skips existing objects and memberships |
| 3 | Databricks Asset Bundles | Three-task pipeline job, Databricks App definition, synchronized source and requirements | Bundle deploy updates its existing deployment |
| 4 | Asset Bundle job and SQL | Security DDL, synthetic submissions, micro ledger, SCD2 history, policy functions, masks, row filters, published view | DDL and merge logic are idempotent; revisions append audit history |
| 5 | Terraform | Table and policy-function grants after those objects exist | Additive grants converge through `grant_tables=true` |
| 6 | Asset Bundle plus account setup | Starts the Databricks App and assigns its managed service principal to the public account group | Existing app is redeployed; existing membership is skipped |
| 7 | `container_apps_deploy.ps1` | ACR, image, Container Apps environment/app, managed identity, Easy Auth registration and token store | Discovers named/random resources and updates them; image is rebuilt intentionally |
| 8 | `sovereignshield_up.ps1` | Health and running-state verification; optional GitHub environment configuration | Verification only unless GitHub configuration is requested |

The staged applies are required. Account-group grants cannot bind until Stage 2
creates the account-level groups, and table grants cannot bind until Stage 4
creates the tables and policy functions.

## User-Owned Workload Resource Group

These are the resources visible in `rg-sovereignshield` immediately after the
Terraform foundation stage.

| Azure resource | Created by | Why it exists | Cost and security relevance | Teardown owner |
| --- | --- | --- | --- | --- |
| `dbw-sovshield` Azure Databricks workspace | Terraform `azurerm_databricks_workspace` | Hosts workspace APIs, jobs, app, SQL warehouse, policies, and UC integration. Premium is required for row filters and column masks. | The workspace object is not the main cost; running job/SQL compute is. | Terraform |
| `dbac-sovereignshield` access connector | Terraform | A system-assigned managed identity used by the UC storage credential. | Avoids storage keys and SAS tokens; no compute charge. | Terraform |
| `stsovshield<suffix>` storage account | Terraform | ADLS Gen2 storage root for the governed catalog and managed volume. | Storage/transactions incur usage cost. Shared-key access and anonymous containers are disabled. | Terraform |
| `metastore` container | Terraform | Storage path presented to Unity Catalog through the external location. | Carries governed files and managed-table storage. | Terraform with storage account |
| `kv-sovereignshield-<suffix>` Key Vault | Terraform | Stores public proxy credentials, tenant ID, and rebuilt workspace URL. | Transaction-based cost; RBAC and purge protection are enabled. | Terraform; soft-deleted name remains during retention |
| Connector storage RBAC assignment | Terraform | Grants the explicit access connector `Storage Blob Data Contributor` on UC storage. | This is the data-plane authorization; creating a connector alone grants no storage access. | Terraform |
| CI/CD and public proxy Entra applications/service principals | Terraform through the Entra provider | CI/CD uses OIDC for deployment; the public proxy authenticates anonymous portal queries to Databricks SQL. | No compute cost. The public proxy has no Azure control-plane role. | Terraform deletes the Entra objects; their Databricks account SCIM records are preserved by default |
| Five Entra persona groups | Terraform through the Entra provider | Names are mirrored into Databricks account groups used by `is_account_group_member()`. | No resource charge. Human membership is deliberately outside Terraform. | Terraform deletes these Entra groups; Databricks account group records are preserved by default |

Terraform also creates Databricks-side resources that do not appear as Azure
tiles: `sc-sovereignshield`, `el-sovereignshield`, Key Vault-backed secret scope
`sovereignshield`, catalog `dbw_sovereignshield`, its three schemas and managed
volume, the dissemination SQL warehouse, and the ingestion cluster policy.

## Databricks-Managed Resource Group

The exact generated names vary on every workspace creation. The items in the
current screenshot have these roles:

| Managed resource | Why Azure Databricks creates it | Operational guidance |
| --- | --- | --- |
| `dbmanagedidentity` | Platform-managed identity used by workspace infrastructure | Distinct from the explicit `dbac-sovereignshield` identity used for project UC storage |
| `dbstorage<suffix>` | Workspace root storage for Databricks-managed artifacts | Not the project's `stsovshield<suffix>` governed catalog storage |
| Event Grid system topic for `dbstorage<suffix>` | Platform event integration attached to managed workspace storage | Databricks-owned; do not repurpose it |
| `workers-vnet` | Managed network for classic Databricks compute | Created with the workspace even before a job cluster starts |
| `workers-sg` | Network security rules for the managed worker network | Do not edit rules manually; workspace operations depend on them |
| `nat-gateway` | Outbound translation for the managed worker network | NAT processing and data transfer can incur Azure charges |
| `nat-gw-public-ip` | Public egress address attached to the NAT gateway | Recreated with the workspace; do not treat it as a permanent institutional endpoint |
| `unity-catalog-access-connector` | Databricks-managed connector supporting workspace UC integration | Separate from the project connector that Terraform binds to external storage |

Classic job clusters may add ephemeral compute resources to this group while a
pipeline is running. Their absence before Stage 4 is normal. SQL Serverless
compute runs in the Databricks serverless plane and does not appear here as a
user-managed VM.

## Why Databricks Account Wiring Exists

Creating Entra groups is not sufficient. Unity Catalog's
`is_account_group_member()` resolves Databricks **account-level** groups, and a
workspace-local group with the same display name does not match.

Stage 2 therefore:

1. Creates or finds the five account-level groups.
2. Creates or finds account user records for the four pre-existing Entra users.
3. Creates or finds Databricks account service-principal records for the CI/CD
   and public proxy Entra applications.
4. Adds each principal to its policy group.
5. Assigns the groups and deployment principal to the new workspace.

These Databricks account records support identity resolution; they are not a
running workspace and do not incur compute cost. They intentionally survive
workload teardown so a rebuilt workspace can be reattached idempotently. The
corresponding Terraform-owned Entra groups, applications, and service principals
are destroyed with the workload and recreated on the next foundation apply;
human Entra users remain client-owned and are never deleted.

## Resources Added by the Serving Stage

Stage 7 currently uses `container_apps_deploy.ps1`, not the optional Terraform
gateway module. It creates or reuses:

| Resource | Purpose | Existing behavior |
| --- | --- | --- |
| `acrsovereignshield<suffix>` | Basic Azure Container Registry containing timestamped portal images | Reuses the first matching registry; always builds a fresh image |
| `cae-sovereignshield` | Consumption Container Apps environment | Reused when present |
| `ca-sovereignshield-portal` | External FastAPI portal, 0.5 CPU/1 GiB, configured for 1-3 replicas | Updated in place when present |
| Container App system identity | Pulls the image and reads Key Vault references | Created with the app and granted only the required roles |
| Easy Auth Entra application/service principal | Supports optional signed-in persona elevation while anonymous access remains enabled | Repaired/converged by the script |
| `stsovereignshieldauth<suffix>` Blob token store | Persists Easy Auth provider tokens across revisions and replicas | Existing matching account is reused |

The app is a consumption workload, not a permanently allocated VM. Its cost is
driven by replica uptime, CPU/memory allocation, requests, registry/storage, and
logs. Pause mode sets minimum replicas to zero; workload teardown deletes the
app, environment, matching registry, and token store.

## Remote State Resource Group

`rg-sovereignshield-tfstate` is created once before Terraform can initialize.
It contains the configured storage account and `tfstate` Blob container. Shared
key access is disabled; operators and CI need `Storage Blob Data Contributor`
on the account.

The setup wrapper validates this backend but does not create it. The normal
workload teardown preserves it because Terraform cannot safely delete the state
store it is currently using and because retained state supports audit and
reconstruction. Delete it only as an explicit final decommissioning decision.

## Destruction Ownership

```powershell
# Preview every destructive ownership path.
powershell.exe -ExecutionPolicy Bypass -File .\sh\sovereignshield_down.ps1 `
  -Mode Workload -WhatIf

# Execute ordered workload teardown.
powershell.exe -ExecutionPolicy Bypass -File .\sh\sovereignshield_down.ps1 `
  -Mode Workload -ConfirmWorkloadDestruction
```

The script discovers live tables and functions before deleting schemas, destroys
bundle resources, handles script-managed or Terraform-managed Container Apps,
runs Terraform destroy, removes an orphaned Databricks diagnostic workspace if
Azure leaves one behind, and verifies both zero Terraform state entries and zero
resources in `rg-sovereignshield` before reporting success.

It preserves the backend and Databricks account identity records. Human Entra
users are never created or deleted by the orchestration scripts.

## Console Review Checklist

After Stage 1:

- `rg-sovereignshield` contains the workspace, project access connector, Key
  Vault, and governed storage account.
- the Databricks managed group is marked **Managed by dbw-sovshield**;
- the workspace reports `Succeeded` and has a workspace URL;
- Terraform outputs include the workspace URL, warehouse ID, submission volume,
  and Key Vault name.

After Stage 2:

- all five groups exist in the Databricks account;
- the four persona users and two project service principals have account records;
- account groups are assigned to the workspace; and
- `is_account_group_member()` can resolve each expected policy name.

After Stage 8:

- the Databricks App reports `RUNNING`;
- the Container Apps health endpoint reports `ok`;
- anonymous access returns only published/free observations;
- signed-in personas return their expected rows and masks; and
- no-group identity verification returns zero rows.

## Source of Truth

| Concern | Authoritative file |
| --- | --- |
| End-to-end setup order | `sh/sovereignshield_up.ps1` |
| Databricks account identity wiring | `sh/databricks_account_setup.ps1` |
| Container Apps and Easy Auth | `sh/container_apps_deploy.ps1` |
| Ordered teardown | `sh/sovereignshield_down.ps1` |
| Terraform dependency graph | `terraform/main.tf` and `terraform/modules/` |
| Job and Databricks App resources | `databricks.yml` |
| Table, view, row-filter, and mask ownership | `src/unity_catalog_triple_lock.sql` |
| Detailed commands and recovery | `docs/AUTOMATION_RUNBOOK.md` and `steps_terraform.md` |