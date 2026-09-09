# Runbook — Terraform path

From an empty subscription to client handover, provisioning with Terraform.

**This is the *how*.** For the *why* — the contractor delivery pattern, the
ownership split, the revocation model and where it stops — read
[docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md).

Following the imperative script path instead? [steps_scripts.md](steps_scripts.md).
They are alternatives, not a sequence. Running both against one subscription
creates resources Terraform did not create and then has to adopt.

Everything here is idempotent. `terraform apply` converges, and re-running is the
normal way to move forward after a partial failure. Credentials are the one thing
never recreated silently: if a service principal exists and its secret is already
in Key Vault, it is left alone. Resetting a credential the pipeline is using
surfaces later as an opaque 401. Use `sh/kv_spn_remediation.sh` when you actually
intend to rotate.

---

## Stage 0 — Local prerequisites

```powershell
az --version                  # Azure CLI
databricks --version          # v1.10+ for apps-in-bundles
terraform version             # v1.9+
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

Open a **new** terminal afterwards — `PATH` does not refresh in the session that
ran the installer — then `gh auth login`. You need admin rights on the
repository; environment protection rules are an admin-only API.

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

Then verify the build works before touching any cloud resource. This is the gate
a contractor reproduces with no credentials at all:

```powershell
pip install -r requirements.txt
pytest tests/                 # expect 70 passed, 12 skipped
```

The skips are the `--live` tests, which need a workspace, and the `--stress`
benchmarks, which take minutes. Both are meant to skip here.

### 0.1 Terraform state backend

A bootstrap resource: it has to exist before the configuration that would
otherwise create it, so Terraform cannot own it. Create it once, by hand.

```powershell
$location     = "canadacentral"
$stateRg      = "rg-sovereignshield-tfstate"
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

> **Pass 2 belongs after Stage 1, not here.** It needs a Databricks workspace
> that does not exist yet. Running it early sets some variables and not others,
> and a partially configured repository fails CI instead of skipping it.

**Pass 2 — after Stage 1.** The two state-backend values are shell variables
from Stage 0.1 and **do not survive a new terminal**, so set them again:

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

./sh/github_environment_setup.ps1 -Repository <owner>/<repo> `
    -Reviewers <github-username> `
    -AzureClientId $appId -AzureTenantId $tenant -AzureSubscriptionId $sub `
    -DatabricksHost $dbHost `
    -TfStateResourceGroup $stateRg `
    -TfStateStorageAccount $stateAccount
```

Every value here is an **identifier, not a secret**. The service principal's
credential stays in Key Vault and is exchanged via OIDC at run time.

Two things the script cannot do for you:

**Protect the `main` branch.** Settings → Branches → require a pull request
before merging. Restricting deployments to protected branches means nothing if
no branch is protected.

**Give you a second reviewer.** `prevent_self_review` is set whenever reviewers
are supplied, so on a solo repository *you cannot approve your own deployment*
and every merge waits indefinitely. Either name a second reviewer, or omit
`-Reviewers` until the gate is genuinely wanted.

---

## Stage 1 — Provision infrastructure

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
> create them.
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

---

## Stage 2 — Databricks account wiring

The most common cause of "the deploy worked but I see no data".

```powershell
./sh/databricks_account_setup.ps1 -AccountId "<your-account-id>"
```

Find the account id at `https://accounts.azuredatabricks.net` (top-right menu).
It is a GUID and it belongs to the Azure tenant, not to any workspace, so it
survives every teardown and rebuild — record it once.

The easy mistake is passing the workspace's numeric org id, the
`7405606562483631` in `adb-7405606562483631.11.azuredatabricks.net`. The CLI
rejects it as `Error: The accountId could not be retrieved`, which reads like a
permissions problem rather than a wrong argument. The script now checks the shape
of the value before it calls anything.

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

The `sovereign_shield` schema is created by the DDL itself in Stage 4.

### 2.1 Attach the persona grants

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

`pre_auth.ps1` discovers the vault by prefix and prints both the workspace it
resolved and the identity it loaded, so a stale URL or an unexpected credential
is visible immediately rather than surfacing as a deploy failure.

The bundle's `submission_volume` variable must match the volume Terraform built.
It defaults to `/Volumes/dbw_sovereignshield/sovereign_submissions/submissions`;
if you changed `catalog_name` or `submissions_schema_name`, pass it:

```powershell
terraform -chdir=terraform output -raw submission_volume_path
databricks bundle deploy -t dev --var="warehouse_id=<id>" --var="submission_volume=<path>"
```

The reporting task writes submissions there and the receiving task reads them, so
a mismatch surfaces as "No submission root at ..." in Stage 4 rather than at
deploy time.

> **The volume is deliberately admin-only.** Unity Catalog volumes support
> neither row filters nor column masks, so `READ VOLUME` returns whole files.
> These files are *more* sensitive than the tables built from them: the SDMx-ML
> carries the unmasked `OBS_VALUE` for every observation `fn_ddm_obs_conf_mask`
> hides, and the accompanying micro CSVs carry the bank-level contributions
> `fn_rls_micro_country_lock` isolates by jurisdiction. That is why the volume
> lives in its own schema with no persona traversal, rather than beside the
> governed tables where every persona already holds `USE SCHEMA`. Granting a
> researcher read here would hand over precisely what the mask exists to
> withhold.

On this path it will report `Identity: Azure CLI user <you>`. That is correct.
Terraform federates the CI/CD principal to GitHub OIDC and deliberately mints no
client secret, so there is no deployment credential to load locally — you deploy
as yourself, and CI deploys as the federated identity. The two are separate by
design: a secret that could be loaded onto a laptop is a secret that can leave
one. If it reports a service principal instead, you are on a vault seeded by
`sh/kv_spn_create.sh`.

Requires an `az login` session in the tenant.

---

## Stage 4 — Run the pipeline

```powershell
databricks bundle run sovereignshield_sdmx_pipeline -t dev
```

Three tasks: security DDL → synthetic submissions → validation and SCD2 merge.
The DDL task is itself idempotent — `CREATE TABLE IF NOT EXISTS` plus a
detach/replace/re-attach cycle for the policy functions, so re-running never
drops history. Verify:

```sql
SELECT BATCH_STATUS, IS_CURRENT, COUNT(*)
FROM dbw_sovereignshield.sovereign_shield.agg_sdmx_history
GROUP BY 1, 2;
```

You should see `PUBLISHED`/`true` rows plus `QUARANTINE`/`false` audit rows from
the revision cycle.

**Now bind the table grants.** The tables exist, so the securables are
resolvable:

```powershell
cd terraform; terraform apply -var="grant_tables=true"; cd ..
```

---

## Stage 5 — Deploy the portal

```powershell
databricks bundle run sovereignshield_portal -t dev
./sh/databricks_account_setup.ps1 -AccountId "<your-account-id>" -AppName sovereignshield-portal
```

Re-running the same script with `-AppName` resolves the app's managed service
principal and adds it to `sg-sovereignshield-public`, skipping everything it
already did.

**Why a second identity:** Databricks Apps mints its *own* managed service
principal and injects those credentials as `DATABRICKS_CLIENT_ID`/`SECRET`.
That — not the Entra `spn-sovereignshield-public` — is what anonymous requests
actually run as. The Entra one is only used by the Container Apps deployment in
Stage 7. Skip this and the fail-closed default returns zero rows, and the portal
renders empty for every visitor.

Restart the app afterwards so it picks up the new membership.

> **On-behalf-of-user SQL queries fail with a bare `"Error during request to
> server"`, even after `whoami` correctly resolves your identity.** The forwarded
> caller token (`X-Forwarded-Access-Token`) defaults to two identity-only scopes
> — `iam.current-user:read`, `iam.access-control:read`. Neither covers opening a
> SQL warehouse session as the caller, which is what every `/api/v1/facets` or
> `/api/v1/export/*` call needs.
>
> The fix is `user_api_scopes: ["sql"]` on the app resource in
> [databricks.yml](databricks.yml) — a `databricks bundle deploy` away, not a
> click in the UI. Two things that look plausible and are not:
> - `user_authorization` in `app.yaml` — the correct-sounding key, wrong file and
>   wrong name. Deploys cleanly, has no effect at all; `databricks apps get`
>   afterwards shows the same two default scopes.
> - The same field passed directly to `databricks apps update --json` — rejected
>   as `unknown field: user_authorization`. Confirms it isn't a syntax problem;
>   the field doesn't exist under that name anywhere in this API. Also: that
>   command is **not** a partial patch despite its per-field flags — a JSON body
>   containing only one field silently dropped this app's `resources` block and
>   `description` on the live app. Recovered with a plain `bundle deploy`, which
>   reconciles both from this file. Use `apps create-update APP_NAME UPDATE_MASK`
>   for a true field-mask patch if you ever need one outside the bundle.
>
> Verify with `databricks apps get sovereignshield-portal` and look for `"sql"`
> in `effective_user_api_scopes` — not just that the deploy succeeded.
>
> Each visitor consents to the scope once, and can't revoke it themselves; an
> admin can pre-consent on their behalf. A workspace-wide allowlist
> (**Settings → Development → Restrict OAuth scopes for apps**) can block a scope
> even from an app that requests it.

> **`Permission Required — You don't have access to the app"`, for any persona
> other than the one who deployed it.** A third, separate authorization layer
> from the two above — this is workspace-level "can this identity open the app
> at all," decided before the request reaches `api_gateway.py`, which is why it
> never shows up in the app's own logs no matter how long you search them.
>
> Deploying an app grants the deployer `CAN_MANAGE` and nobody else anything.
> Every persona group needs `CAN_USE` declared explicitly, as `permissions` on
> the app resource in [databricks.yml](databricks.yml):
>
> ```yaml
> permissions:
>   - group_name: "sg-sovereignshield-admin"
>     level: "CAN_MANAGE"
>   - group_name: "sg-sovereignshield-researchers"
>     level: "CAN_USE"
>   # ... one entry per persona group
> ```
>
> This is admission, not entitlement — the same split as the SQL grants.
> `CAN_USE` only lets a group load the app; Unity Catalog's row filter and
> column mask still decide what that session can see once inside. Verify with
> `databricks apps get-permissions sovereignshield-portal` and confirm every
> persona group appears with `CAN_USE`, rather than trusting that the deploy
> succeeded.
>
> **"Sign out" appears to do nothing.** It isn't broken — a Databricks App has
> no session of its own to end. The workspace SSO session lives at the browser's
> Azure AD scope, which no app-level route can clear; `SOVEREIGNSHIELD_SIGNOUT_URL`
> is `/` on this path for exactly that reason. A fresh incognito window per
> persona, which is what you're already doing, is the correct way to test more
> than one persona in one browser. Real per-app sign-out (`/.auth/logout`) only
> exists behind Stage 7's Container Apps front door.

> **`databricks.sql.exc.RequestError: Error during request to server` remains
> after SQL consent and app `CAN_USE` are correct.** The SQL warehouse is a
> separate securable from both the app and Unity Catalog. Verify its own ACL:
>
> ```powershell
> databricks warehouses get-permissions <warehouse-id> --output json
> ```
>
> Every persona group must have `CAN_USE`. The durable Terraform fix is to set
> both deferred toggles in `terraform.tfvars` and reconcile them after the
> account groups and tables exist:
>
> ```powershell
> cd terraform
> # account_groups_ready = true
> # grant_tables         = true
> terraform apply -var-file="terraform.tfvars"
> cd ..
> ```
>
> Do not diagnose this as a Unity Catalog row-filter failure until the
> warehouse ACL is present. Admin access can hide this defect because the
> deploying owner can use the warehouse without a persona grant.

> **The researcher sees populated facets but search fails while submitters
> work.** Researchers retain published `C`/`N` rows so the column mask can
> redact their values. The caller therefore needs `EXECUTE` on
> `fn_ddm_obs_conf_mask`, not only `SELECT` on `agg_sdmx_history`. The pipeline
> applies this grant from `src/unity_catalog_grants.sql`; redeploy the bundle
> and rerun the security/pipeline task if the grant is missing. Verify the
> expected result: all published countries remain visible, restricted values
> render as `restricted`, and quarantined rows remain absent.

---

## Stage 6 — Verify the persona matrix

Open the app URL from `databricks apps get`. What to check, in order:

| Sign in as | Expected badge | Expected data |
|---|---|---|
| `econ_researcher` | Researcher (Published Series, Confidential Values Masked) | All countries; some values show `restricted`, and the header reports a withheld count |
| `boc_analyst` | Bank of Canada Analyst (Full Sovereign Access) | CA rows in full incl. confidential values; other countries only `PUBLISHED`+`F`. The amber "Include my quarantined batches" card appears |
| `fed_analyst` | Federal Reserve Analyst | Mirror image — **US confidential values visible, CA confidential values masked**. This is the cross-sovereign leak the mask exists to prevent; verify it explicitly |
| `admin_lead` | Platform Administrator | Everything, including quarantined batches |

Then click **Export SDMX-ML 3.0**. The download is round-tripped through the
SDMx reader before it's returned, so a 422 means the payload failed validation
rather than the browser choking.

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

A Databricks App always sits behind workspace SSO, so its "public" tier is an
authenticated visitor holding no sovereign entitlement. Azure Container Apps
is the only way to see a genuinely unauthenticated visitor. Choose **one** of
the two deployment paths below. They use the same resource names and must not
both be run against one subscription.

### 7.1 Recommended: script deployment

```powershell
az account show --query "{subscription:id, tenant:tenantId, name:name}" -o table

./sh/container_apps_deploy.ps1 `
  -KeyVaultName "<key-vault-name>" `
  -DatabricksHost "<workspace-url-without-https>" `
  -WarehouseId "<warehouse-id>" `
  -ResourceGroup "<resource-group>" `
  -Location "<azure-region>"
```

The values are identifiers, not secrets. Resolve them for the current
subscription rather than copying them into documentation:

```powershell
az keyvault list --query "[].name" -o table
az databricks workspace show --name <workspace-name> --resource-group <resource-group> --query workspaceUrl -o tsv
terraform -chdir=terraform output -raw sql_warehouse_id
```

Leave off `-EnableEntraSignIn` for the anonymous public-data test. The script
builds the image, creates or updates Container Apps, wires Key Vault, and
prints the portal URL. It is idempotent; rerunning it rolls out a new image.
If a first run stops after the image build, rerun the same command; its existing
`acrsovereignshield*` registry is discovered automatically.

Verify the URL printed by the script:

```powershell
$gatewayUrl = "https://<fqdn-printed-by-the-script>"
Invoke-RestMethod "$gatewayUrl/api/v1/health"
$result = Invoke-RestMethod "$gatewayUrl/api/v1/search?limit=500"
$result.observations | ForEach-Object { "{0} {1}" -f $_.BATCH_STATUS, $_.OBS_CONF }
```

Every returned row must have `BATCH_STATUS=PUBLISHED` and `OBS_CONF=F`.
The script detects the Key Vault authorization mode and uses either the RBAC
role assignment or the legacy access-policy command, never both.
The Container App uses Azure service-principal authentication with an explicit
tenant ID and `DATABRICKS_AUTH_TYPE=azure-client-secret`; this is separate from
the Databricks App's on-behalf-of OAuth flow.

When `-EnableEntraSignIn` is used, the script also grants admin consent for the
AzureDatabricks `user_impersonation` delegated permission. The operator must
have permission to grant consent in the tenant.

If the public endpoint reports `invalid_client`, run the public credential
repair before rerunning the Container Apps script:

```powershell
bash sh/kv_spn_create.sh
```

The repair checks both Key Vault and the Entra app. It replaces a stale Key
Vault secret only when the app has no credential, then the Container Apps
script refreshes its Key Vault references.

### 7.2 Terraform-managed alternative

Use this path only if Container Apps must be part of Terraform state. Build and
push the image first, then enable the module:

```powershell
# Build and push to a registry Terraform can pull from.
az acr create -n <registry> -g rg-sovereignshield --sku Basic
az acr build -r <registry> -t sovereignshield-portal:latest .

cd terraform
terraform apply `
    -var="deploy_dissemination_gateway=true" `
    -var="gateway_image=<registry>.azurecr.io/sovereignshield-portal:latest"
terraform output -raw dissemination_gateway_url
cd ..
```

The Terraform module creates the same named Container Apps resources as the
script, so do not run this after 7.1 unless existing resources have been
removed or deliberately imported into Terraform state.

`gateway_image` is validated at plan time when the toggle is on, so a missing
image fails in seconds rather than after a multi-minute rollout ending in a DNS
error.

Requires `spn-sovereignshield-public` in the Databricks account and in
`sg-sovereignshield-public` — handled by Stage 2.

Verify the anonymous tier is genuinely fail-closed. Every observation returned
must carry `BATCH_STATUS=PUBLISHED` and `OBS_CONF=F`:

```bash
curl -s "https://<fqdn>/api/v1/search?limit=5" | jq '.observations[] | {BATCH_STATUS, OBS_CONF}'
```

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
pytest tests/                    # offline: 70 passed
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

```powershell
# 1. Rotate the deployment credential. Any copy you retained dies immediately;
#    the pipeline keeps working because secrets are resolved by NAME.
cd terraform
terraform apply -replace="module.identity.azuread_service_principal_password.public_proxy"
cd ..

# 2. Remove your Key Vault role assignment.
az role assignment delete --assignee "<your-object-id>" `
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

Order matters, and the first step is the one that is easy to get wrong.

`databricks bundle destroy` removes what the *bundle* declares — the job, the app,
the uploaded files. It does **not** drop the tables, functions, or the view: those
were created imperatively by a job run, not declared as bundle resources, so
nothing in the bundle knows they exist. Terraform will not drop them either;
`force_destroy = false` on the catalog and schema is deliberate, so that a
`terraform destroy` can never silently discard populated tables.

The result is that skipping the explicit drops fails late, after Terraform has
already destroyed the service principals and Key Vault secrets:

```
Error: cannot delete schema: Schema 'dbw_sovereignshield.sovereign_shield' is not
empty. The schema has 3 tables(s), 3 functions(s), 0 volumes(s)
```

```powershell
# 1. Data and policy plane. Dependency order: the view reads the history table, and
#    both tables bind the policy functions, which cannot be dropped while bound.
#    These are Unity Catalog API calls - no warehouse or cluster needs to be running.
. .\sh\pre_auth.ps1
$published = "dbw_sovereignshield.sovereign_shield"
$intake    = "dbw_sovereignshield.sovereign_intake"
databricks tables    delete "$published.v_agg_sdmx_published"
databricks tables    delete "$published.agg_sdmx_history"
databricks tables    delete "$intake.lbs_micro_transactions"
databricks functions delete "$published.fn_ddm_obs_conf_mask"
databricks functions delete "$published.fn_rls_multi_persona_lock"
databricks functions delete "$intake.fn_rls_micro_country_lock"

# 2. Bundle-declared resources: the job definition, the app, the workspace files.
databricks bundle destroy -t dev

# 3. Release the table grants, if grant_tables was ever set true.
cd terraform
terraform apply -var="grant_tables=false"

# 4. Everything Terraform owns: gateway, warehouse, catalog, schemas, workspace,
#    storage, Key Vault, service principals, Entra groups. This includes the
#    submissions volume and everything filed in it - the archive of what was
#    received is destroyed with it, so copy anything you need first.
terraform destroy
cd ..

# 5. Nothing to purge. purge_protection_enabled is on, so the soft-deleted vault
#    cannot be purged before its 90-day retention expires - that is the guarantee
#    the setting exists to make. It is free, and the next deployment gets a fresh
#    random suffix, so it collides with nothing. Leave it.
az keyvault list-deleted --query "[].{name:name,purgeable:properties.purgeProtectionEnabled}" -o table
```

> **Run step 1 before step 4, not after.** Terraform destroys the Key Vault secrets
> early, so once step 4 has failed, `pre_auth.ps1` can no longer resolve the
> workspace URL. Recovering means reading it back from ARM:
>
> ```powershell
> $url = az databricks workspace show -n dbw-sovshield -g rg-sovereignshield --query workspaceUrl -o tsv
> $env:DATABRICKS_HOST = "https://$($url.Trim())"
> $env:DATABRICKS_AUTH_TYPE = "azure-cli"
> ```

> **Let step 4 finish.** With `deploy_dissemination_gateway = true`, the Container
> Apps managed environment routinely reports `Still destroying...` for ten to
> twenty minutes while it tears down its underlying infrastructure. That is normal,
> not a hang.
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
| Key Vault (soft-deleted) | `purge_protection_enabled` is deliberate — it stops an accidental or malicious destroy discarding secrets permanently | **Nothing.** A purge-protected vault cannot be purged early; it self-deletes after 90 days |
| The resource group, when `create_resource_group = false` | Terraform never owned it, so it does not destroy it | `az group delete -n rg-sovereignshield` |
| **The Unity Catalog catalog, if destroy was interrupted** | Catalogs are metastore-scoped and outlive the workspace. An orphan holds its name and is unreachable from any live workspace | See troubleshooting below |

Account-level identities surviving is usually what you want: a rebuild becomes
near-instant and Stage 2 collapses to `[skip]` lines. Remove them only when the
engagement is genuinely over.

### 9.4 Confirm nothing is billing

```powershell
az resource list --resource-group rg-sovereignshield --output table
az keyvault list-deleted --query "[].name" -o tsv
```

An empty resource list means teardown is complete. The soft-deleted vault will
still be listed and that is expected — `az keyvault purge` on it returns
`(MethodNotAllowed) Operation 'DeletedVaultPurge' is not allowed`, because purge
protection is doing what it was enabled to do. It costs nothing and the vault
name carries a random suffix, so it never blocks a rebuild.

If the resource group lingers, `az group delete -n rg-sovereignshield` — but run
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

### An orphaned catalog blocks the apply

`cannot create catalog: Catalog 'dbw_sovereignshield' already exists`, and
importing it fails with `not accessible in current workspace`.

The catalog survives in the metastore, bound (`ISOLATED`) to a workspace that no
longer exists, and owned by that workspace's admin group — which now has no
members. No live workspace can reach it.

```powershell
# 1. Become metastore admin: accounts.azuredatabricks.net -> Catalog ->
#    metastore_azure_canadacentral -> set Owner to yourself.

# 2. Unbind it from the dead workspace, then take ownership and remove it.
databricks catalogs update dbw_sovereignshield --isolation-mode OPEN
databricks catalogs update dbw_sovereignshield --owner "<your-upn>"
databricks catalogs delete dbw_sovereignshield --force
```

`--isolation-mode OPEN` first is the part people miss: delete fails while the
catalog is still bound to the dead workspace.

Do not import it instead. Its `storage_root` points at the old workspace's
managed storage, and `storage_root` is immutable — Terraform would plan a
destroy-and-recreate and land you back here.

### Other failures

**`Error: Cannot apply incomplete plan`.** The plan errored, so the saved file is
unusable. Fix the underlying error and re-run `terraform plan -out=tfplan` — a
stale `tfplan` cannot be salvaged.

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

**`terraform apply` reports 409 `MissingSubscriptionRegistration`.** The
subscription has never used that resource provider. Register it and re-apply —
no state surgery is needed, the apply is resumable:

```powershell
az provider register --namespace Microsoft.App
az provider show --namespace Microsoft.App --query registrationState -o tsv
```

Stage 0 registers the full set up front so this does not interrupt an apply
half-way through.

**`terraform apply` reports 403 `KeyBasedAuthenticationNotPermitted` on the
Unity Catalog storage account.** The account is created with
`shared_access_key_enabled = false` on purpose, and the provider was falling
back to key auth for its data-plane poll. `providers.tf` sets
`storage_use_azuread = true` to force Entra ID instead. If you still see it,
confirm that setting survived a `terraform init -upgrade`.

**`terraform apply` says a resource "already exists - to be managed via Terraform
this resource needs to be imported".** Something outside this configuration
created it. For the resource group, set `create_resource_group = false` and
re-plan. For anything else, adopt it explicitly rather than deleting it:

```powershell
terraform import azurerm_resource_group.main "/subscriptions/<sub>/resourceGroups/rg-sovereignshield"
```

Deleting the conflicting resource is usually the wrong move here. The Key Vault
carries `purge_protection_enabled`, so a destroy-and-recreate cycle leaves the
name reserved and the next apply fails on a soft-deleted vault.

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

**A script fails with "running scripts is disabled on this system".** The
execution policy is `Restricted`. See Stage 0 —
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`. Note
that VS Code's PowerShell Extension terminal bypasses the policy, so the same
script can work there and fail in a plain terminal.

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

**`Secret 'spn-client-id' is missing`.** An older `pre_auth.ps1` that assumed
every vault holds a CI/CD client secret. Terraform never creates one — the
principal is OIDC-only. Pull the current script, which falls back to your Azure
CLI session on this path.

**`Identity: Azure CLI user` and then a 403.** The signed-in operator is not a
workspace admin. Deploying the workspace as subscription Owner does not grant
that implicitly on a workspace someone else created — add yourself under
**Settings → Identity and access**.

**`UC_AZURE_CREDENTIAL_NOT_FOUND` — "the access connector may have been deleted
or recreated".** Unity Catalog stores an internal `credential_id` resolved when
the storage credential was created. Recreating the access connector leaves that
handle dangling even though the ARM resource ID string is unchanged, so Azure
looks entirely healthy. Confirm before changing anything:

```powershell
$json = @{ storage_credential_name = "sc-sovereignshield"; external_location_name = "el-sovereignshield" } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText("$PWD\val.json", $json, (New-Object System.Text.UTF8Encoding($false)))
databricks api post /api/2.1/unity-catalog/validate-storage-credentials --json "@val.json"
```

Re-setting the connector ID to the same value forces UC to re-resolve it. Check
the reported dependent-table count first — `force` is safe at zero, and a signal
to stop and think if not:

```powershell
databricks storage-credentials update sc-sovereignshield --json '{"force":true,"azure_managed_identity":{"access_connector_id":"<connector-arm-id>"}}'
```

A changed `credential_id` in the response confirms the rebind.

**"This Azure storage request is not authorized — Firewalls and virtual networks".**
The storage account is unreachable from compute. Serverless SQL egresses from the
Databricks serverless plane and classic compute from the Databricks-managed VNet;
neither can be admitted by an IP rule, a VNet rule, or an access-connector
resource instance rule. `public_network_access_enabled` must stay `true` unless
the workspace is VNet-injected with private endpoints. This costs less than it
looks: `shared_access_key_enabled = false` and no anonymous container mean every
request still needs an Entra token that RBAC allows.

**`cannot create catalog: Catalog '<name>' already exists`, on a fresh metastore.**
Not leftover state. Databricks auto-provisions a default catalog for a new
workspace, named after the workspace with hyphens converted to underscores, so a
workspace called `dbw-sovereignshield` produces a catalog `dbw_sovereignshield`.

`workspace_name` is `dbw-sovshield` precisely so the two cannot converge, and a
validation on `catalog_name` now fails the plan rather than the apply if they ever
do. You should only meet this on a deployment predating that change.

Whether it bites is a race, which is why the same configuration can deploy once
and fail on rebuild. If the name is already taken when the workspace is created,
Databricks appends the org id instead (`dbw_sovereignshield_7405618511341043`) and
the two coexist unnoticed. Tear that catalog down and the name is free, so the
next workspace claims it first.

Confirm which catalog you have before deleting anything — the auto-created one has
a `storage_root` under the workspace's own managed storage rather than the
external location, and is owned by the workspace admins group:

```powershell
databricks catalogs get dbw_sovereignshield --output json |
  ConvertFrom-Json | Select-Object name, owner, storage_root
```

A `storage_root` of `abfss://unity-catalog-storage@dbstorage...` is the platform's
catalog and holds nothing of yours. Drop it and re-run the apply:

```powershell
databricks catalogs delete dbw_sovereignshield --force
```

**`cannot configure default credentials` on `databricks_*` reads, while `az` is
logged in and working.** Not a credential problem. Check the plan for the
workspace being replaced:

```
~ workspace_url = "https://adb-..." -> (known after apply)
```

The Databricks provider takes `azure_workspace_resource_id` from the workspace
this configuration manages, so during a replacement that id is unknown and the
provider has no host. It falls back to default auth, finds only `ARM_TENANT_ID`,
and reports a credentials error for what is really an unknown target. Every
failure will be a *read* — refreshing resources that already exist.

Anything that replaces the workspace therefore needs the provider told where to
look, because it can no longer work it out. `workspace_name` is force-new, so
renaming it is the usual trigger. Point `DATABRICKS_HOST` at the workspace that
still exists, and the provider configures from the environment instead of from
the unknown attribute:

```powershell
$url = az databricks workspace show -n <current-workspace-name> -g rg-sovereignshield --query workspaceUrl -o tsv
$env:DATABRICKS_HOST = "https://" + $url.Trim()
$env:DATABRICKS_AUTH_TYPE = "azure-cli"

terraform destroy -target="module.unity_catalog_governance" -target="module.databricks_workspace" -var-file="terraform.tfvars"

# Clear it before the rebuild: after the rename this names a workspace that no
# longer exists, and the apply fails with "Did not find workspace with specified
# org ID" - see the entry below.
Remove-Item Env:DATABRICKS_HOST, Env:DATABRICKS_AUTH_TYPE
terraform apply -var-file="terraform.tfvars"
```

Leave the identity module out of the targets — recreating the Entra groups would
issue new object ids and break the account-level group assignments made in
Stage 2.

If the destroy has already failed and left the state half-owned, the fallback is
to take the Databricks resources out of state so nothing needs refreshing through
the provider at all. **Delete the metastore-scoped ones first.** The external
location and storage credential outlive the workspace, so a `state rm` alone
leaves them holding their names against the rebuild:

```powershell
databricks external-locations  delete el-sovereignshield --force
databricks storage-credentials delete sc-sovereignshield --force
terraform state rm module.databricks_workspace.databricks_external_location.main `
                   module.databricks_workspace.databricks_storage_credential.main `
                   module.databricks_workspace.databricks_cluster_policy.ingestion `
                   module.databricks_workspace.databricks_secret_scope.key_vault `
                   module.unity_catalog_governance.databricks_sql_endpoint.dissemination
```

The cluster policy, secret scope and warehouse are workspace-scoped and die with
the workspace, so they need removing from state but not deleting. The subsequent
apply recreates all of them, and creates tolerate a deferred provider
configuration where reads do not.

**`Did not find workspace with specified org ID`, on a workspace that exists.**
A stale `DATABRICKS_HOST` in the shell. The Databricks provider reads its ambient
environment and that takes precedence over `azure_workspace_resource_id` in
[terraform/providers.tf](terraform/providers.tf), so the provider talks to
whatever workspace the variable names — and the org ID in the error is the *old*
workspace's, not the one being built.

This is structural rather than unlucky: Stage 3 dot-sources `pre_auth.ps1`
specifically to set `DATABRICKS_HOST`, so any Terraform run later in that same
shell inherits it. After a rebuild it points at a workspace that no longer exists.

```powershell
Get-ChildItem Env: | Where-Object Name -like "DATABRICKS*"
Remove-Item Env:DATABRICKS_HOST, Env:DATABRICKS_AUTH_TYPE, Env:DATABRICKS_AZURE_RESOURCE_ID, Env:DATABRICKS_ACCOUNT_ID -ErrorAction SilentlyContinue
```

Run Terraform in a shell that has never sourced `pre_auth.ps1`, or clear the
variables first. The provider is fully configured from `providers.tf` and needs
none of them.

**`terraform destroy` fails with "schema is not empty".** The tables, functions
and view are still there. `databricks bundle destroy` does not remove them — it
only removes what the bundle declares, and those objects were created by a job
run. Drop them explicitly as in Stage 9.2 step 1, then re-run the destroy.

**"cannot delete external location ... N dependent managed tables"**, with no
catalog left that could hold them. They are tombstones: Unity Catalog counts
dropped managed tables as dependents until their undrop retention window expires,
so the count survives the catalog and accumulates across redeployments.

`force_destroy = true` is set on the external location and storage credential for
exactly this, but it is **read from state, not from configuration**, so adding it
mid-teardown does not help the destroy already in progress. Applying it first is
worse: by that point the Key Vault is gone, and a targeted apply tries to rebuild
it. Delete the two out of band and let the next refresh notice:

```powershell
databricks external-locations   delete el-sovereignshield --force
databricks storage-credentials  delete sc-sovereignshield --force
```

Safe because the guard that protects live data is upstream and has already run:
`force_destroy = false` on the catalog and schema is what raises the "schema is
not empty" error above, so nothing live can remain by the time these are reached.
A deployment created after this fix carries the flag in state and tears down
without the manual step.

---

## What re-running does

| Command | Re-run behaviour |
|---|---|
| `terraform apply` | Converges. Reports drift on anything it owns; never touches policy objects |
| `terraform_reconcile.ps1` | Reads state against reality and imports or forgets. Changes nothing in the cloud |
| `databricks bundle deploy` | Re-applies DDL idempotently: `CREATE TABLE IF NOT EXISTS` plus detach → replace → re-attach for policy functions |
| `databricks_account_setup.ps1` | Reuses account identities; adds missing memberships and workspace assignments |
| `github_environment_setup.ps1` | Reports what already matches and changes only drift |
| `pre_auth.ps1` | Read-only. Discovers the vault and loads credentials into the current session |

---

## Cost control

Between sessions, Stage 9.1 is the cheap pause. `terraform destroy` is the full
teardown; see Stage 9.2 for the ordering that avoids a dependency error.
