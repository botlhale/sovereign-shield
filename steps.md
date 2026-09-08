# Runbook — from empty subscription to client handover

The complete operational sequence. Start at Stage 0 with nothing provisioned and
finish at Stage 9 with the platform running and handed over.

**This is the *how*.** For the *why* — the contractor delivery pattern, the
ownership split, the revocation model and where it stops — read
[docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md).

Two provisioning paths are supported and they are alternatives, not a sequence:

| | Path A — Terraform | Path B — Scripts |
| --- | --- | --- |
| Use when | Production, CI/CD, repeatable | A demo, a laptop, first look |
| Owns | Identity, workspace, catalog, warehouse, gateway | The same, imperatively |
| State | Remote azurerm backend | None |
| Re-run | `terraform apply` converges | Idempotent: prints `[skip]` / `[create]` |

Everything is idempotent either way. Credentials are the one thing never
recreated silently: if a service principal exists and its secret is already in
Key Vault, both paths leave it alone. Resetting a credential the pipeline is
using surfaces later as an opaque 401. Use `sh/kv_spn_remediation.sh` when you
actually intend to rotate.

---

## Stage 0 — Local prerequisites

```powershell
az --version                  # Azure CLI
databricks --version          # v1.10+ for apps-in-bundles
terraform version             # v1.9+ for Path A only
python --version              # 3.11+
gh --version                  # GitHub CLI, for Stage 0.2 only

az login
az account set --subscription "<your-subscription>"

# `az databricks` lives in an extension. Without it, the first command that
# needs it stops on an interactive "install now? (Y/n)" prompt, which looks
# like a hang when the prompt is not visible.
az extension add --name databricks --upgrade
az config set extension.use_dynamic_install=yes_without_prompt

# Resource providers are registered per subscription, and a fresh subscription
# has most of them off. Terraform surfaces this late, as a 409
# MissingSubscriptionRegistration part-way through an apply.
foreach ($ns in @(
    "Microsoft.Databricks",
    "Microsoft.App",                # Container Apps, Stage 7
    "Microsoft.OperationalInsights", # Log Analytics, required by Container Apps
    "Microsoft.KeyVault",
    "Microsoft.Storage",
    "Microsoft.ManagedIdentity"
)) {
    az provider register --namespace $ns
}

# Registration is asynchronous. Confirm all report Registered before Stage 1.
az provider list --query "[?namespace=='Microsoft.Databricks' || namespace=='Microsoft.App' || namespace=='Microsoft.OperationalInsights'].{ns:namespace, state:registrationState}" -o table
```

Missing the GitHub CLI:

```powershell
winget install --id GitHub.cli --exact
```

Every `sh/*.ps1` script in this runbook is blocked until PowerShell is allowed to
run local scripts. Windows ships as `Restricted`, which permits none:

```powershell
Get-ExecutionPolicy -List                      # LocalMachine Restricted is the default
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

`CurrentUser` scope needs no admin rights. Prefer setting the policy over
`powershell -ExecutionPolicy Bypass -File ...`: Stage 3 dot-sources
`pre_auth.ps1` to load credentials into the *current* session, and a child
process would discard them on exit.

VS Code's PowerShell Extension terminal launches with `Bypass` already applied,
so a script that runs there can still fail in an ordinary terminal.

Open a **new** terminal afterwards — `PATH` does not refresh in the session that
ran the installer — then `gh auth login`. You need admin rights on the
repository; environment protection rules are an admin-only API.

Then verify the build works before touching any cloud resource. This is the gate
a contractor reproduces with no credentials at all:

```powershell
pip install -r requirements.txt
pytest tests/                 # expect 59 passed, 12 skipped
```

The skips are the `--live` tests, which need a workspace, and the `--stress`
benchmarks, which take minutes. Both are meant to skip here.

### 0.1 Terraform state backend (Path A only)

A bootstrap resource: it has to exist before the configuration that would
otherwise create it, so Terraform cannot own it. Create it once, by hand.

```powershell
$location    = "canadacentral"
$stateRg     = "rg-sovereignshield-tfstate"
$stateAccount = "st<something-globally-unique>"   # 3-24 chars, lowercase alphanumeric

# Storage account names are globally unique across all of Azure. Check first.
az storage account check-name --name $stateAccount --query nameAvailable -o tsv

az group create --name $stateRg --location $location

az storage account create `
    --name $stateAccount `
    --resource-group $stateRg `
    --location $location `
    --sku Standard_LRS `
    --allow-blob-public-access false `
    --allow-shared-key-access false `
    --min-tls-version TLS1_2

az storage container create `
    --name tfstate `
    --account-name $stateAccount `
    --auth-mode login
```

`--allow-shared-key-access false` is the reason `backend.hcl.example` sets
`use_azuread_auth = true`. There is no account key to leak or rotate, so
Terraform and CI both authenticate as themselves. `--auth-mode login` on the
container create is required for the same reason: without a key, the CLI has to
use your Entra identity.

Which means every identity that runs Terraform needs a **data-plane** role on
this account. Subscription Owner is not enough — Owner is a control-plane role
and grants nothing inside the blob service:

```powershell
$scope = az storage account show -n $stateAccount -g $stateRg --query id -o tsv

# You, for local runs.
$me = az ad signed-in-user show --query id -o tsv
az role assignment create --assignee-object-id $me --assignee-principal-type User `
    --role "Storage Blob Data Contributor" --scope $scope

# The CI service principal, for the promotion workflow. Skip until Stage 1
# creates it; come back and run this before the first CI deployment.
$cicd = az ad sp list --display-name spn-sovereignshield-cicd --query "[0].id" -o tsv
if ($cicd) {
    az role assignment create --assignee-object-id $cicd --assignee-principal-type ServicePrincipal `
        --role "Storage Blob Data Contributor" --scope $scope
}
```

Without this, `terraform init` fails at *"Failed to get existing workspaces:
listing blobs: ... 403 AuthorizationPermissionMismatch"*. Role assignments take
up to a few minutes to propagate.

State holds resource identifiers and should be treated as sensitive even though
this configuration keeps credentials out of it.

> **Teardown note.** This resource group is deliberately outside
> `terraform destroy`. Stage 9 removes it separately.

### 0.2 GitHub repository controls (CI only)

Skip if you are deploying by hand. Required before the promotion workflow means
anything.

GitHub creates an environment implicitly the first time a job references one,
**with no protection rules attached**. Without this step `environment: production`
is decorative: the workflow looks like it has a human gate while every merge
deploys straight through.

**Run it in two passes.** The workflow's preflight job treats the repository
variables as all-or-nothing — all six set means deploy, none set means skip
cleanly, and *some* set fails the run naming the gap. The Databricks host is not
knowable until Stage 1 creates the workspace, so setting it now would either be
wrong or leave the repository half-configured.

**Pass 1 — now.** Protection rules only, no variables:

```powershell
./sh/github_environment_setup.ps1 -Repository <owner>/<repo> `
    -Reviewers <github-username>
```

Blank variables are skipped by design, so preflight stays at `configured=false`
and CI skips deployment cleanly instead of failing.

> **Pass 2 belongs at the end of Stage 4, not here.** It needs a Databricks
> workspace that does not exist yet. Running it early sets some variables and
> not others, and a partially configured repository fails CI instead of skipping
> it. Come back once Stage 1 has finished.

**Pass 2 — after Stage 1.** Re-run with every value filled in. The script is
idempotent; it reports what already matches and changes only drift.

The two state-backend values are shell variables from Stage 0.1. **They do not
survive a new terminal**, so set them again rather than assuming they are still
in scope:

```powershell
$stateRg      = "rg-sovereignshield-tfstate"
$stateAccount = "<the account you created in Stage 0.1>"

$dbHost = az databricks workspace list --query "[0].workspaceUrl" -o tsv
$sub    = az account show --query id -o tsv
$tenant = az account show --query tenantId -o tsv
$appId  = az ad sp list --display-name spn-sovereignshield-cicd --query "[0].appId" -o tsv

# Every value must be non-empty. An empty one is silently skipped by the script
# and leaves the repository half-configured, which fails the workflow's
# preflight rather than skipping it.
@{ appId = $appId; tenant = $tenant; sub = $sub; dbHost = $dbHost;
   stateRg = $stateRg; stateAccount = $stateAccount }.GetEnumerator() |
  ForEach-Object { "{0,-13} {1}" -f $_.Key, $(if ($_.Value) { $_.Value } else { "<<< EMPTY >>>" }) }
```

If `dbHost` is empty the workspace does not exist yet. If `appId` is empty the
service principal was never created, or carries a different display name.
Resolve both before continuing.

```powershell
./sh/github_environment_setup.ps1 -Repository <owner>/<repo> `
    -Reviewers <github-username> `
    -AzureClientId $appId -AzureTenantId $tenant -AzureSubscriptionId $sub `
    -DatabricksHost $dbHost `
    -TfStateResourceGroup $stateRg `
    -TfStateStorageAccount $stateAccount
```

Every value here is an **identifier, not a secret**. The service principal's
credential stays in Key Vault and is exchanged via OIDC at run time.

The script sets required reviewers, prevents self-review, restricts deployments
to protected branches, and writes the repository variables the workflow reads.

Two things it cannot do for you:

**Protect the `main` branch.** Settings → Branches → require a pull request
before merging. Restricting deployments to protected branches means nothing if
no branch is protected.

**Give you a second reviewer.** `prevent_self_review` is set whenever reviewers
are supplied, so on a solo repository *you cannot approve your own deployment*
and every merge waits indefinitely. Either name a second reviewer, or omit
`-Reviewers` until the gate is genuinely wanted.

---

## Stage 1 — Provision infrastructure

### Path A — Terraform (recommended)

```powershell
cd terraform
cp backend.hcl.example backend.hcl              # edit: the state account from Stage 0.1
cp terraform.tfvars.example terraform.tfvars    # edit: subscription_id, tenant_id

terraform init -backend-config="backend.hcl"
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
cd ..
```

> **If `rg-sovereignshield` already exists**, set `create_resource_group = false`
> in `terraform.tfvars` before planning. Terraform then reads the group instead
> of creating it. This is the normal setting in a regulated estate, where a
> landing zone owns resource groups and the workload identity has no rights to
> create them, and it is also correct after running the `sh/` quickstart.
>
> Two consequences: `location` is ignored in favour of the group's own region,
> and `terraform destroy` leaves the group in place.

Provisions the resource group, Entra persona groups, both service principals,
the GitHub OIDC federated credentials, Key Vault, the Databricks workspace,
the access connector and storage credential, the catalog and schema, and the
serverless SQL warehouse.

**Three toggles stay `false` on this first apply.** Each one depends on
something that does not exist yet, and Terraform cannot tell you that in advance
— it discovers it mid-apply, after other resources are already created:

| Toggle | Blocked by | Flip it after |
| --- | --- | --- |
| `account_groups_ready` | Databricks resolves principals against its own account directory, not Entra ID | Stage 2 |
| `grant_tables` | Tables are created by the Asset Bundle; a grant on a missing securable fails | Stage 4 |
| `deploy_dissemination_gateway` | Needs a container image that is built and pushed later | Stage 7 |

Re-applying is cheap and idempotent, so the sequence is: apply, run the stage
that satisfies the dependency, flip one toggle, apply again.

Capture what the next stages need:

```powershell
cd terraform
terraform output -raw sql_warehouse_id
terraform output -raw workspace_url
terraform output persona_groups
terraform output next_steps
cd ..
```

### Path B — Scripts

```bash
bash sh/kv_spn_create.sh        # RG, Key Vault (discovered by prefix), both SPNs
bash sh/grp_users_create.sh     # 5 Entra groups, 4 persona users, memberships
bash sh/kv_spn_create.sh        # re-run: adds the proxy SPN to the public group
bash sh/databricks_create.sh    # workspace + publishes its URL to Key Vault
```

The second `kv_spn_create.sh` run is not a typo. On a first pass the public group
does not exist yet, so the proxy service principal cannot be added to it; the
re-run fills that gap and skips everything else.

`databricks_create.sh` is the step that matters most after a teardown: a rebuilt
workspace has a **different URL**, and a stale `databricks-workspace-url` secret
authenticates against a workspace that no longer exists.

Then create the SQL warehouse by hand — **SQL Warehouses → Create**, serverless,
2X-Small, auto-stop 10 minutes — and copy its ID from Connection Details.

---

## Stage 2 — Databricks account wiring

Required on **both** paths, and the most common cause of "the deploy worked but I
see no data".

```powershell
./sh/databricks_account_setup.ps1 -AccountId "<your-account-id>"
```

Find the account id at `https://accounts.azuredatabricks.net` (top-right menu).

It ensures account-level users, service principals and groups exist, fixes
memberships, and assigns everything to the new workspace (`USER` for groups,
`ADMIN` for the pipeline principal).

Two things worth knowing:

- **Account scope is not workspace scope.** `is_account_group_member()` only
  resolves account-level groups. Groups created at workspace scope look
  identical in the UI and will never match, so the filter falls through to its
  fail-closed default and returns zero rows.
- **Deleting the workspace did not delete these.** Your account users, groups
  and service principals are almost certainly still there, so expect this run to
  be mostly `[skip]` with new workspace assignments.

The script authenticates with your interactive `az login` identity, not the
CI/CD service principal — an Entra Global Administrator is automatically a
Databricks account admin, which avoids the bootstrap problem where the SPN
cannot grant itself the access it needs. It temporarily suppresses the `ARM_*`
variables so they can't shadow that, and restores them on exit.

Then confirm the catalog exists:

```sql
SHOW CATALOGS;   -- expect dbw_sovereignshield
```

Azure auto-creates a default catalog named after the workspace, and Path A
creates it explicitly. If it is absent on Path B, create it and make the SPN
owner before proceeding. The `sovereign_shield` schema is created by the DDL
itself.

### 2.1 Attach the persona grants (Path A)

The groups now exist in the Databricks account, so Terraform can grant against
them. This is the first of the deferred toggles from Stage 1:

```powershell
cd terraform
terraform apply -var="account_groups_ready=true"
cd ..
```

Set `account_groups_ready = true` in `terraform.tfvars` so later applies keep it.
Skipping this leaves the catalog and warehouse reachable by nobody but the
deploying principal, which reads as a broken deployment rather than a missing
step.

---

## Stage 3 — Deploy the bundle

```powershell
. .\sh\pre_auth.ps1        # dot-sourced — the leading dot is load-bearing
databricks bundle validate -t dev
databricks bundle deploy -t dev --var="warehouse_id=<warehouse-id>"
```

`pre_auth.ps1` discovers the vault by prefix and prints the workspace it
resolved, so a stale URL is visible immediately rather than surfacing as a
deploy failure.

---

## Stage 4 — Run the pipeline

```powershell
databricks bundle run sovereignshield_sdmx_pipeline -t dev
```

Three tasks: security DDL → synthetic submissions → validation and SCD2 merge. The DDL task is itself idempotent — `CREATE TABLE IF NOT EXISTS` plus a detach/replace/re-attach cycle for the policy functions, so re-running never drops history. Verify:

```sql
SELECT BATCH_STATUS, IS_CURRENT, COUNT(*)
FROM dbw_sovereignshield.sovereign_shield.agg_sdmx_history
GROUP BY 1, 2;
```

You should see `PUBLISHED`/`true` rows plus `QUARANTINE`/`false` audit rows from the revision cycle.

**Path A only — now bind the table grants.** The tables exist, so the securables
are resolvable:

```powershell
cd terraform; terraform apply -var="grant_tables=true"; cd ..
```

---

## Stage 5 — Deploy the portal

```powershell
databricks bundle run sovereignshield_portal -t dev
./sh/databricks_account_setup.ps1 -AccountId "<your-account-id>" -AppName sovereignshield-portal
```

The second command is the one that used to be a manual account-console step. Re-running the same script with `-AppName` resolves the app's managed service principal and adds it to `sg-sovereignshield-public`, skipping everything it already did.

**Why a second identity:** Databricks Apps mints its *own* managed service principal and injects those credentials as `DATABRICKS_CLIENT_ID`/`SECRET`. That — not the Entra `spn-sovereignshield-public` — is what anonymous requests actually run as. The Entra one is only used by the Container Apps deployment in Stage 7. Skip this and the fail-closed default returns zero rows, and the portal renders empty for every visitor.

Restart the app afterwards so it picks up the new membership.

---

## Stage 6 — Verify the persona matrix

Open the app URL from `databricks apps get`. What to check, in order:

| Sign in as | Expected badge | Expected data |
|---|---|---|
| `econ_researcher` | Researcher (Published Series, Confidential Values Masked) | All countries; some values show `restricted`, and the header reports a withheld count |
| `boc_analyst` | Bank of Canada Analyst (Full Sovereign Access) | CA rows in full incl. confidential values; other countries only `PUBLISHED`+`F`. The amber "Include my quarantined batches" card appears |
| `fed_analyst` | Federal Reserve Analyst | Mirror image — **US confidential values visible, CA confidential values masked**. This is the cross-sovereign leak the mask exists to prevent; verify it explicitly |
| `admin_lead` | Platform Administrator | Everything, including quarantined batches |

Then click **Export SDMX-ML 3.0**. The download is round-tripped through the SDMx reader before it's returned, so a 422 means the payload failed validation rather than the browser choking.

Direct API check:

```powershell
curl "https://<app-url>/api/v1/health"
curl "https://<app-url>/api/v1/search?reporting_country=CA&limit=5"
```

Finally, run the same assertions the offline suite makes, but against the real
metastore. This is the run that detects drift between the pandas mirror in
`uc_query.LocalDeltaBackend` and the deployed policy:

```powershell
$env:DATABRICKS_SERVER_HOSTNAME = "<workspace-url-without-https>"
$env:DATABRICKS_WAREHOUSE_ID    = "<warehouse-id>"
$env:SOVEREIGNSHIELD_TEST_TOKEN_CA = "<a token for a submitter-ca principal>"
pytest tests/ --live
```

---

## Stage 7 — Optional: genuinely anonymous access

```powershell
./sh/container_apps_deploy.ps1 -KeyVaultName "<your-kv>" `
    -DatabricksHost "<workspace-url-without-https>" `
    -WarehouseId "<warehouse-id>"
```

Also idempotent: it discovers an existing `acrsovereignshield*` registry, reuses the Container Apps environment, and `update`s the app rather than failing if it already exists. The image is always rebuilt, since shipping new code is the point of re-running.

This is the only way to see a genuinely unauthenticated visitor, since a Databricks App always sits behind workspace SSO. Requires `spn-sovereignshield-public` in the Databricks account and in `sg-sovereignshield-public` — handled by Stage 2.

On Path A this is provisioned by `module.dissemination_gateway` instead; set
`gateway_image` in `terraform.tfvars` and read the URL from
`terraform output -raw dissemination_gateway_url`.

---

## Stage 8 — Hand over to the client

The deliverable is the **repository**, not the data and not your credentials.
The client deploys it with their own identity, into their own subscription,
against their own catalog.

### 8.1 What you hand over

| Artefact | Why it is safe to transfer |
| --- | --- |
| The Git repository | Contains no credential and no observation. `pytest tests/test_secret_decoupling.py` asserts this on every commit |
| `terraform/` + `terraform.tfvars.example` | Names and locations only; no variable can carry a secret |
| `databricks.yml` | Reproduces the pipeline in any workspace |
| `.github/skills/` | The specifications the implementation is measured against |
| `docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md` | The governance framework for their own future engagements |

You do **not** hand over `terraform.tfvars`, `backend.hcl`, `sh/spn_details`,
`sh/databricks_details`, or any `.tfstate`. All are gitignored.

### 8.2 Client-side verification

The client runs this inside their own boundary, on their own data:

```powershell
pytest tests/                    # offline: 59 passed
terraform plan                   # expect no diff against policy objects
databricks bundle validate -t dev
```

`terraform plan` showing a diff on a row filter or column mask means the
ownership boundary has been violated — those belong to the SQL DDL, and
Terraform must not be managing them.

Then the substantive check: re-run the generator inside their boundary and diff
the resulting schema against their production metadata. Because every control is
attached to Unity Catalog objects rather than embedded in pipeline logic, the
controls activate on real data at first run. There is no "productionisation"
phase in which the security model is re-implemented, and therefore no phase in
which it can be re-implemented incorrectly.

### 8.3 Revoke your own access

Three actions. None of them touches the delivered code.

```bash
# 1. Rotate the deployment credential. Any copy you retained dies immediately;
#    the pipeline keeps working because secrets are resolved by NAME.
bash sh/kv_spn_remediation.sh

# 2. Remove your Key Vault role assignment.
az role assignment delete --assignee "<your-object-id>" \
  --scope "$(az keyvault show --name <vault> --query id -o tsv)"

# 3. Remove yourself from every persona group, in Entra AND in the
#    Databricks account.
az ad group member remove --group "sg-sovereignshield-admin" --member-id "<your-object-id>"
```

### 8.4 Prove the revocation

This is the step that distinguishes a claim from a guarantee:

```powershell
curl -H "Authorization: Bearer <your-old-token>" "https://<app-url>/api/v1/search?limit=5"
```

Expect `row_count: 0` with `persona: "public"`, or a `401`. **Not an error about
permissions** — the row filter grants rows only on positive group membership and
fails closed, so a former builder resolves to zero groups and therefore zero
rows.

> Off-boarding a contractor and enforcing sovereignty between two nations are
> the same code path. There is no separate revocation feature that could rot, be
> forgotten, or be tested less rigorously than the primary one.

### 8.5 Handover checklist

- [ ] `pytest tests/` passes on the client's machine with no cloud credentials
- [ ] `pytest tests/ --live` passes for all four personas against their workspace
- [ ] `terraform plan` shows no diff against policy objects
- [ ] Rotation exercised once, and the pipeline still deploys afterwards
- [ ] Client administrator has run `databricks_account_setup.ps1` themselves
- [ ] Your group memberships and Key Vault role assignments are removed
- [ ] A query as your removed identity returns **zero rows**, not an error
- [ ] Client has read the "Where this model stops" section of the playbook

---

## Stage 9 — Teardown

### 9.1 Pause between demos

Costs nothing to resume, and keeps every identity and grant intact:

```powershell
databricks apps stop sovereignshield-portal
cd terraform; terraform apply -var="deploy_dissemination_gateway=false"; cd ..
```

The SQL warehouse auto-stops after 10 idle minutes on its own, and the job
cluster is spot-priced and terminates on completion. What stays billable is the
storage account and Key Vault — pennies.

### 9.2 Full teardown

Order matters. Terraform does not own the tables or the policy bindings, so it
cannot remove them, and Unity Catalog refuses to drop a schema whose tables carry
live row filters. Destroying in the wrong order produces a dependency error that
does not name the cause.

```powershell
# 1. Data and policy plane: tables, policy UDFs, row filters, masks, the view.
databricks bundle destroy -t dev

# 2. Release the table grants so those securables are no longer referenced.
cd terraform
terraform apply -var="grant_tables=false"

# 3. Everything Terraform owns: gateway, warehouse, catalog, schema, workspace,
#    storage, Key Vault, service principals, Entra groups.
terraform destroy
cd ..

# 4. Purge the soft-deleted vault. purge_protection_enabled is on, so the vault
#    survives destroy by design and its name stays reserved until purged.
az keyvault purge --name <vault-name> --location canadacentral
```

> **Let step 3 finish.** The Container Apps managed environment routinely reports
> `Still destroying...` for ten to twenty minutes while it tears down its
> underlying infrastructure. That is normal, not a hang.
>
> Interrupting it is the single most expensive mistake available here: the
> resource ends up half-deleted while state still believes it exists, and
> recovering means hand-editing state. If you need the demo gone quickly, prefer
> `az group delete -n rg-sovereignshield --no-wait` and then reconcile state, over
> Ctrl-C during a destroy.

### 9.3 What survives, and why

| Resource | Why Terraform leaves it | Remove with |
| --- | --- | --- |
| Databricks **account** groups and service principals | Account scope; the provider is workspace-scoped | Account console, or reverse `databricks_account_setup.ps1` |
| Entra persona **users** | Never created by Terraform — membership is an administrative act with its own approval path | `az ad user delete --id boc_analyst@<tenant>` |
| Terraform state storage account | Bootstrap resource, created before the configuration existed | `az group delete -n rg-sovereignshield-tfstate` |
| Key Vault (soft-deleted) | `purge_protection_enabled` is deliberate — it stops an accidental destroy discarding secrets other environments reference | `az keyvault purge` |
| The resource group, when `create_resource_group = false` | Terraform never owned it, so it does not destroy it | `az group delete -n rg-sovereignshield` |

Account-level identities surviving is usually what you want: a rebuild becomes
near-instant and Stage 2 collapses to `[skip]` lines. Remove them only when the
engagement is genuinely over.

### 9.4 Confirm nothing is billing

```powershell
az resource list --resource-group rg-sovereignshield --output table
az keyvault list-deleted --query "[].name" -o tsv
```

An empty resource list and a purged vault means teardown is complete. If the
resource group lingers, `az group delete -n rg-sovereignshield` — but run
`terraform destroy` first so state stays consistent with reality. Deleting the
group behind Terraform's back leaves state describing resources that no longer
exist, and the next `apply` fails on refresh.

---

## When it doesn't work

### Recovering after an interrupted apply or an out-of-band deletion

Terraform assumes it is the only writer. When that breaks — a destroy is
interrupted, a resource group is emptied in the portal, an apply fails half-way
— state and reality diverge in one of two directions, and the errors look
unrelated to each other:

| Symptom | Meaning | Fix |
| --- | --- | --- |
| `cannot configure default credentials` / `failed to get the workspace_id` | State holds an object whose provider can no longer authenticate | `terraform state rm` |
| `already exists - to be managed via Terraform this resource needs to be imported` | The object exists, state does not know it | `terraform import` |
| `Storage Credential '...' already exists` | Same, for a Unity Catalog object | `terraform import` |

Run the reconciler rather than doing this by hand. It reads state, compares it
against Azure and the metastore, and imports or forgets each resource
accordingly. It changes nothing in the cloud:

```powershell
./sh/terraform_reconcile.ps1 -WhatIf     # report only
./sh/terraform_reconcile.ps1
terraform -chdir=terraform plan -out=tfplan
```

**Scope is the thing that catches people out.** Unity Catalog objects live in the
**metastore**, which is account-level, so a catalog, storage credential or
external location *outlives the workspace that created it*. Cluster policies,
secret scopes and SQL warehouses are workspace-scoped and die with it.

Deleting a workspace therefore orphans the first group and destroys the second.
Removing all of them from state — the correct move for the workspace-scoped ones
— strands the metastore objects, and the next apply fails on "already exists".
The reconciler encodes that distinction so it does not have to be remembered.

Key Vault secrets come back for a different reason: the vault is created with
purge protection, so deleting it soft-deletes it, and
`recover_soft_deleted_key_vaults = true` restores it complete with every secret.
The vault reappears; state does not.

**`Error: Cannot apply incomplete plan`.** The plan errored, so the saved file is
unusable. Fix the underlying error and re-run `terraform plan -out=tfplan` — a
stale `tfplan` cannot be salvaged.

**A destroy sits on `Still destroying... azurerm_container_app_environment`.**
Ten to twenty minutes is normal; the managed environment tears down its
infrastructure before reporting. **Do not interrupt it.** Ctrl-C mid-delete
leaves the resource half-gone and state believing it exists, which is how most
of the failures above start.

### Other failures

**`cannot create catalog: metastore_id must be empty or equal to the metastore id
assigned to the workspace`.** A workspace is bound to exactly one metastore and
the provider resolves it from the workspace it is configured against, so the
catalog must not set `metastore_id` at all. Passing the workspace's Azure
resource id looks plausible and is a different identifier entirely.

**`cannot create permissions: Principal: GroupName(...) does not exist`.** The
group exists in Entra ID but not in the Databricks *account* directory, which is
where Databricks resolves principals. Run Stage 2, then re-apply with
`account_groups_ready=true`.

**Container App fails with `failed to resolve registry ... no such host`.** The
image does not exist. `deploy_dissemination_gateway` must stay `false` until
Stage 7 builds and pushes one; `gateway_image` is validated at plan time when
the toggle is on.

**`cannot create external location: ... does not have READ, LIST, WRITE, DELETE
permissions`.** Azure RBAC is eventually consistent. The access connector's
`Storage Blob Data Contributor` grant exists, but the storage data plane has not
observed it yet, and Unity Catalog validates a credential the moment it is
created by issuing a HEAD against the container.

`depends_on` cannot fix this — it orders API calls, not propagation. The module
inserts a `time_sleep` between the role assignment and the credential. If it
still fails, raise the wait and re-apply:

```powershell
terraform apply -var="rbac_propagation_wait=300s"
```

Re-applying alone often succeeds, because by then the assignment has propagated.

**`terraform apply` reports 409 `MissingSubscriptionRegistration`.** The
subscription has never used that resource provider. Register it and re-apply —
no state surgery is needed, the apply is resumable:

```powershell
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider show --namespace Microsoft.App --query registrationState -o tsv
```

Registration is asynchronous and takes a minute or two. Stage 0 registers the
full set up front so this does not interrupt an apply half-way through.

**`terraform apply` reports 403 `KeyBasedAuthenticationNotPermitted` on the
Unity Catalog storage account.** The account is created with
`shared_access_key_enabled = false` on purpose, and the provider was falling
back to key auth for its data-plane poll. `providers.tf` sets
`storage_use_azuread = true` to force Entra ID instead. If you still see it,
confirm that setting survived a `terraform init -upgrade`.

**`terraform apply` says a resource "already exists - to be managed via Terraform
this resource needs to be imported".** Something outside this configuration
created it, usually the `sh/` quickstart. For the resource group, set
`create_resource_group = false` and re-plan; Terraform reads it instead of
creating it. For anything else, adopt it explicitly rather than deleting it:

```powershell
terraform import azurerm_resource_group.main "/subscriptions/<sub>/resourceGroups/rg-sovereignshield"
```

Deleting the conflicting resource is usually the wrong move here. The Key Vault
carries `purge_protection_enabled`, so a destroy-and-recreate cycle leaves the
name reserved and the next apply fails on a soft-deleted vault.

**A script fails with "running scripts is disabled on this system".** The
execution policy is `Restricted`. See Stage 0 —
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`. Note
that VS Code's PowerShell Extension terminal bypasses the policy, so the same
script can work there and fail in a plain terminal.

**`terraform init` reports "Too many command line arguments. Did you mean to use
-chdir?"** Windows PowerShell splits an unquoted native-command argument
containing `=`, so Terraform receives `backend.hcl` as a stray positional. Quote
the whole token:

```powershell
terraform init -backend-config="backend.hcl"      # quoted
```

**`terraform init` reports 403 `AuthorizationPermissionMismatch`.** The identity
running Terraform has no data-plane role on the state storage account.
Subscription Owner does not grant blob access — assign **Storage Blob Data
Contributor** as shown in Stage 0.1, then wait a few minutes for propagation.

**An `az databricks ...` command appears to hang** after printing two extension
warnings. It is waiting on a hidden `install now? (Y/n)` prompt. Ctrl-C, then
`az extension add --name databricks --upgrade`.

**The portal renders empty for a persona that should see rows.** Almost always
account groups created at *workspace* scope. They look identical in the UI:

```powershell
databricks account groups list --filter "displayName eq 'sg-sovereignshield-public'"
```

An empty result is the diagnosis. `is_account_group_member()` resolves account
scope only, so the row filter falls through to its fail-closed default.

**`terraform apply` wants to change a row filter or mask.** The ownership
boundary has been violated — those belong to `unity_catalog_triple_lock.sql`.
Terraform must not manage them, or it fights the pipeline on every run.

**The bundle deploy 401s.** A stale `databricks-workspace-url` in Key Vault,
pointing at a workspace that no longer exists. `pre_auth.ps1` prints the
workspace it resolved for exactly this reason.

**`terraform destroy` fails on the catalog.** Step 1 of the teardown was skipped;
tables still carry live row filters.

---

## What re-running does

| Command | Re-run behaviour |
|---|---|
| `terraform apply` | Converges. Reports drift on anything it owns; never touches policy objects |
| `databricks bundle deploy` | Re-applies DDL idempotently: `CREATE TABLE IF NOT EXISTS` plus detach → replace → re-attach for policy functions |
| `kv_spn_create.sh` | Reuses RG, vault, both SPNs. Mints a credential **only** if its vault secret is missing |
| `databricks_create.sh` | Reuses the workspace; always refreshes `databricks-workspace-url` if it changed |
| `grp_users_create.sh` | Reuses groups and users; never resets an existing password |
| `databricks_account_setup.ps1` | Reuses account identities; adds missing memberships and workspace assignments |
| `container_apps_deploy.ps1` | Reuses registry, environment and app; always rebuilds and rolls out the image |
| `kv_spn_remediation.sh` | **Destructive by design** — deletes the app registration and rotates credentials |

---

## Cost control

Between sessions, Stage 9.1 is the cheap pause. `terraform destroy` is the full
teardown; see Stage 9.2 for the ordering that avoids a dependency error.