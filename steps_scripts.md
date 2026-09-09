# Runbook — script path

From an empty subscription to a running demo, provisioning imperatively with the
`sh/` scripts. No Terraform, no remote state.

**This is the *how*.** For the *why* — the contractor delivery pattern, the
ownership split, the revocation model and where it stops — read
[docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md).

Using Terraform instead? [steps_terraform.md](steps_terraform.md). They are
alternatives, not a sequence. Running both against one subscription creates
resources Terraform did not create and then has to adopt.

> **This path is a quickstart, not the deployment path.** It exists so a demo can
> be stood up on a laptop without a state backend. It provisions no CI/CD
> promotion, no cluster policy, and no declarative record of what exists. For
> production, CI, or anything reproducible, use the Terraform path.

Every script is idempotent and prints `[skip]` / `[create]` so a re-run is safe
and readable. Credentials are the one thing never recreated silently: if a
service principal exists and its secret is already in Key Vault, the script
leaves it alone. Resetting a credential the pipeline is using surfaces later as
an opaque 401. Use `sh/kv_spn_remediation.sh` when you actually intend to rotate.

---

## Stage 0 — Local prerequisites

```powershell
az --version                  # Azure CLI
databricks --version          # v1.10+ for apps-in-bundles
python --version              # 3.11+

az login
az account set --subscription "<your-subscription>"

# `az databricks` lives in an extension. Without it, the first command that
# needs it stops on an interactive "install now? (Y/n)" prompt, which looks
# like a hang when the prompt is not visible.
az extension add --name databricks --upgrade
az config set extension.use_dynamic_install=yes_without_prompt

# Resource providers are registered per subscription, and a fresh subscription
# has most of them off. Each one surfaces late, as a 409 part-way through a
# script that has already created other resources.
foreach ($ns in @(
    "Microsoft.Databricks",
    "Microsoft.App",                 # Container Apps, Stage 7
    "Microsoft.OperationalInsights", # Log Analytics, required by Container Apps
    "Microsoft.KeyVault",
    "Microsoft.Storage",
    "Microsoft.ManagedIdentity"
)) {
    az provider register --namespace $ns
}

az provider list --query "[?namespace=='Microsoft.Databricks' || namespace=='Microsoft.App'].{ns:namespace, state:registrationState}" -o table
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

The `.sh` scripts need bash. On Windows, Git Bash at
`C:\Program Files\Git\bin\bash.exe` is sufficient.

Then verify the build works before touching any cloud resource. This is the gate
a contractor reproduces with no credentials at all:

```powershell
pip install -r requirements.txt
pytest tests/                 # expect 59 passed, 12 skipped
```

The skips are the `--live` tests, which need a workspace, and the `--stress`
benchmarks, which take minutes. Both are meant to skip here.

---

## Stage 1 — Provision infrastructure

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

The scripts write `sh/spn_details` and `sh/databricks_details` recording what was
created. Both are gitignored and hold identifiers, not secrets.

---

## Stage 2 — Databricks account wiring

The most common cause of "the deploy worked but I see no data".

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

Then confirm a catalog exists:

```sql
SHOW CATALOGS;
```

Azure auto-creates a default catalog when a workspace is assigned to a metastore,
named `<workspace>_<workspace-id>`. On this path nothing creates
`dbw_sovereignshield` for you, so create it and make the pipeline service
principal its owner before proceeding:

```sql
CREATE CATALOG IF NOT EXISTS dbw_sovereignshield;
ALTER CATALOG dbw_sovereignshield OWNER TO `spn-sovereignshield-cicd`;
```

The `sovereign_shield` schema is created by the DDL itself in Stage 4.

Grants are applied by `src/unity_catalog_grants.sql`, which
`sh/apply_security.py` runs as part of the pipeline. On the Terraform path that
file is skipped because Terraform owns the access-control plane; here it is the
only thing that applies grants, so leave `SOVEREIGNSHIELD_SKIP_GRANTS` unset.

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

Table grants are applied by the same run, since `unity_catalog_grants.sql` is
part of the DDL task on this path.

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

```powershell
./sh/container_apps_deploy.ps1 -KeyVaultName "<your-kv>" `
    -DatabricksHost "<workspace-url-without-https>" `
    -WarehouseId "<warehouse-id>"
```

Idempotent: it discovers an existing `acrsovereignshield*` registry, reuses the
Container Apps environment, and `update`s the app rather than failing if it
already exists. The image is always rebuilt, since shipping new code is the point
of re-running.

This is the only way to see a genuinely unauthenticated visitor, since a
Databricks App always sits behind workspace SSO. Requires
`spn-sovereignshield-public` in the Databricks account and in
`sg-sovereignshield-public` — handled by Stage 2.

Add `-EnableEntraSignIn` to layer Container Apps built-in authentication over the
anonymous tier, so signed-in visitors elevate to their real persona.

> **The one manual step.** The Entra token forwarded by built-in authentication
> must be issued for the **AzureDatabricks** resource
> (`2ff814a6-3304-4ab8-85cb-cd0e6f879c1d`), which means adding
> `scope=openid profile 2ff814a6-.../user_impersonation` to the login parameters.
> Miss it and every signed-in visitor silently stays on the public tier — the
> failure is invisible, because falling back to the public persona is exactly
> what the gateway does when it has no usable token.

Verify the anonymous tier is genuinely fail-closed. Every observation returned
must carry `BATCH_STATUS=PUBLISHED` and `OBS_CONF=F`:

```bash
curl -s "https://<fqdn>/api/v1/search?limit=5" | jq '.observations[] | {BATCH_STATUS, OBS_CONF}'
```

---

## Stage 8 — Hand over to the client

The deliverable is the **repository**, not the data and not your credentials.

> On this path there is no declarative record of what was provisioned. If the
> engagement is a real handover rather than a demo, rebuild it on the Terraform
> path first — the client needs something they can `plan` against, not a
> transcript of commands you ran.

### 8.1 What you hand over

| Artefact | Why it is safe to transfer |
| --- | --- |
| The Git repository | Contains no credential and no observation. `pytest tests/test_secret_decoupling.py` asserts this on every commit |
| `databricks.yml` | Reproduces the pipeline in any workspace |
| `.github/skills/` | The specifications the implementation is measured against |
| `docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md` | The governance framework for their own future engagements |

You do **not** hand over `sh/spn_details` or `sh/databricks_details`. Both are
gitignored.

### 8.2 Client-side verification

```powershell
pytest tests/                    # offline: 59 passed
databricks bundle validate -t dev
```

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
- [ ] Rotation exercised once, and the pipeline still deploys afterwards
- [ ] Client administrator has run `databricks_account_setup.ps1` themselves
- [ ] Your group memberships and Key Vault role assignments are removed
- [ ] A query as your removed identity returns **zero rows**, not an error
- [ ] Client has read the "Where this model stops" section of the playbook

---

## Stage 9 — Teardown

Nothing here is declarative, so teardown is manual and order still matters. The
one non-obvious part: `databricks bundle destroy` removes what the *bundle*
declares — the job, the app, the uploaded files — and not the tables, functions
or view, which a job run created imperatively. Those have to go first, and in
dependency order, because Unity Catalog will not drop a policy function while a
table still binds it through a row filter or column mask.

### 9.1 Pause between demos

```powershell
databricks apps stop sovereignshield-portal
az containerapp update -n ca-sovereignshield-portal -g rg-sovereignshield --min-replicas 0
```

The SQL warehouse auto-stops after 10 idle minutes on its own, and the job
cluster is spot-priced and terminates on completion. What stays billable is the
storage account and Key Vault — pennies.

### 9.2 Full teardown

```powershell
# 1. Data and policy plane. Unity Catalog API calls, so nothing needs to be running.
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

# 3. The catalog. Metastore-scoped, so it outlives the workspace - leaving it
#    behind means its name is taken on the next rebuild.
databricks catalogs delete dbw_sovereignshield --force

# 4. Everything in the resource group.
az group delete -n rg-sovereignshield --yes

# 5. The vault soft-deletes. Whether it can be purged depends on how it was created:
#    a vault with purge protection cannot be purged before its retention expires.
az keyvault list-deleted --query "[].{name:name,protected:properties.purgeProtectionEnabled}" -o table
az keyvault purge --name <vault-name> --location canadacentral   # only if not protected
```

Step 2 is the one that is easy to skip and expensive to skip. A catalog left in
the metastore is bound to the workspace you just deleted, owned by that
workspace's admin group, and unreachable from any live workspace — recovering it
needs metastore-admin surgery. See the troubleshooting section.

### 9.3 What survives, and why

| Resource | Why | Remove with |
| --- | --- | --- |
| Databricks **account** groups and service principals | Account scope, outside the workspace | Account console, or reverse `databricks_account_setup.ps1` |
| Entra persona **users** | Membership is an administrative act with its own approval path | `az ad user delete --id boc_analyst@<tenant>` |
| Key Vault (soft-deleted) | Purge protection stops an accidental delete discarding secrets other environments reference | `az keyvault purge` |
| The Unity Catalog catalog | Metastore-scoped; deleting the workspace does not remove it | Step 2 above |

Account-level identities surviving is usually what you want: a rebuild becomes
near-instant and Stage 2 collapses to `[skip]` lines.

### 9.4 Confirm nothing is billing

```powershell
az resource list --resource-group rg-sovereignshield --output table
az keyvault list-deleted --query "[].name" -o tsv
databricks catalogs list -o json | Select-String '"name"'
```

An empty resource list, a purged vault, and no `dbw_sovereignshield` catalog
means teardown is complete.

---

## When it doesn't work

### An orphaned catalog blocks the rebuild

`Catalog 'dbw_sovereignshield' already exists`, and you cannot see it in Catalog
Explorer.

Catalogs are **metastore-scoped**, so one survives the workspace that created it.
It stays bound (`ISOLATED`) to that dead workspace and owned by its admin group,
which now has no members — so no live workspace can reach it.

```powershell
# 1. Become metastore admin: accounts.azuredatabricks.net -> Catalog ->
#    metastore_azure_canadacentral -> set Owner to yourself.

# 2. Unbind it from the dead workspace, then take ownership and remove it.
databricks catalogs update dbw_sovereignshield --isolation-mode OPEN
databricks catalogs update dbw_sovereignshield --owner "<your-upn>"
databricks catalogs delete dbw_sovereignshield --force
```

`--isolation-mode OPEN` first is the part people miss: delete fails while the
catalog is still bound to the dead workspace. Stage 9.2 step 2 exists to stop
this happening at all.

### Other failures

**A script fails with "running scripts is disabled on this system".** The
execution policy is `Restricted`. See Stage 0 —
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`. Note
that VS Code's PowerShell Extension terminal bypasses the policy, so the same
script can work there and fail in a plain terminal.

**An `az databricks ...` command appears to hang** after printing two extension
warnings. It is waiting on a hidden `install now? (Y/n)` prompt. Ctrl-C, then
`az extension add --name databricks --upgrade`.

**A 409 `MissingSubscriptionRegistration`.** The subscription has never used that
resource provider. Register it and re-run — the scripts are idempotent and will
skip what already exists:

```powershell
az provider register --namespace Microsoft.App
az provider show --namespace Microsoft.App --query registrationState -o tsv
```

**The portal renders empty for a persona that should see rows.** Almost always
account groups created at *workspace* scope. They look identical in the UI:

```powershell
databricks account groups list --filter "displayName eq 'sg-sovereignshield-public'"
```

An empty result is the diagnosis. `is_account_group_member()` resolves account
scope only, so the row filter falls through to its fail-closed default.

**The bundle deploy 401s.** A stale `databricks-workspace-url` in Key Vault,
pointing at a workspace that no longer exists. Re-run
`bash sh/databricks_create.sh`, which refreshes the secret. `pre_auth.ps1` prints
the workspace it resolved for exactly this reason.

**`kv_spn_create.sh` did not add the proxy SPN to the public group.** Expected on
a first pass — the group does not exist yet. Re-run it after
`grp_users_create.sh`, as Stage 1 shows.

**A persona user cannot sign in.** `grp_users_create.sh` never resets an existing
password. Reset it in Entra ID, or delete the user and re-run.

**Dropping the schema fails.** The tables, functions and view are still present.
`databricks bundle destroy` does not remove them: it removes what the bundle
declares, and those objects were created by a job run. Drop them explicitly with
`databricks tables delete` and `databricks functions delete` first — the view
before the history table it reads, and both tables before the policy functions
they bind.

---

## What re-running does

| Command | Re-run behaviour |
|---|---|
| `kv_spn_create.sh` | Reuses RG, vault, both SPNs. Mints a credential **only** if its vault secret is missing |
| `databricks_create.sh` | Reuses the workspace; always refreshes `databricks-workspace-url` if it changed |
| `grp_users_create.sh` | Reuses groups and users; never resets an existing password |
| `databricks_account_setup.ps1` | Reuses account identities; adds missing memberships and workspace assignments |
| `container_apps_deploy.ps1` | Reuses registry, environment and app; always rebuilds and rolls out the image |
| `databricks bundle deploy` | Re-applies DDL idempotently: `CREATE TABLE IF NOT EXISTS` plus detach → replace → re-attach for policy functions |
| `pre_auth.ps1` | Read-only. Discovers the vault and loads credentials into the current session |
| `kv_spn_remediation.sh` | **Destructive by design** — deletes the app registration and rotates credentials |

---

## Cost control

Between sessions, Stage 9.1 is the cheap pause. Stage 9.2 is the full teardown —
do not skip step 2, or the next rebuild collides with an orphaned catalog.
