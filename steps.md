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

az login
az account set --subscription "<your-subscription>"
```

Then verify the build works before touching any cloud resource. This is the gate
a contractor reproduces with no credentials at all:

```powershell
pip install -r requirements.txt
pytest tests/                 # expect 59 passed, 2 skipped
```

The 2 skips are the `--live` tests; they need a workspace and are meant to skip
here.

### 0.1 GitHub repository controls (CI only)

Skip if you are deploying by hand. Required before the promotion workflow means
anything:

```powershell
./sh/github_environment_setup.ps1 -Repository <owner>/<repo> `
    -Reviewers <github-username> `
    -AzureClientId <app-id> -AzureTenantId <tenant> -AzureSubscriptionId <sub> `
    -DatabricksHost <workspace-host> `
    -TfStateResourceGroup rg-sovereignshield-tfstate `
    -TfStateStorageAccount <state-storage-account>
```

GitHub creates an environment implicitly the first time a job references one,
**with no protection rules attached**. Without this step `environment: production`
is decorative: the workflow looks like it has a human gate while every merge
deploys straight through.

The script sets required reviewers, prevents self-review, restricts deployments
to protected branches, and writes the repository variables the workflow reads.

One thing it cannot do for you: **protect the `main` branch**. Settings → Branches
→ require a pull request before merging. Restricting deployments to protected
branches means nothing if no branch is protected.

---

## Stage 1 — Provision infrastructure

### Path A — Terraform (recommended)

```powershell
cd terraform
cp backend.hcl.example backend.hcl              # edit: your state storage account
cp terraform.tfvars.example terraform.tfvars    # edit: subscription_id, tenant_id

terraform init -backend-config=backend.hcl
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
cd ..
```

Provisions the resource group, Entra persona groups, both service principals,
the GitHub OIDC federated credentials, Key Vault, the Databricks workspace,
the access connector and storage credential, the catalog and schema, and the
serverless SQL warehouse.

Leave `grant_tables = false` for now. Tables are created by the Asset Bundle in
Stage 4, and a grant against a securable that does not yet exist fails the apply.

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
FROM dbw_sovereignshield.sovereign_shield.lbs_sdmx_history
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

### 9.3 What survives, and why

| Resource | Why Terraform leaves it | Remove with |
| --- | --- | --- |
| Databricks **account** groups and service principals | Account scope; the provider is workspace-scoped | Account console, or reverse `databricks_account_setup.ps1` |
| Entra persona **users** | Never created by Terraform — membership is an administrative act with its own approval path | `az ad user delete --id boc_analyst@<tenant>` |
| Terraform state storage account | Bootstrap resource, created before the configuration existed | `az group delete -n rg-sovereignshield-tfstate` |
| Key Vault (soft-deleted) | `purge_protection_enabled` is deliberate — it stops an accidental destroy discarding secrets other environments reference | `az keyvault purge` |

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