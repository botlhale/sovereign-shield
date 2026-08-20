# Rebuild & test runbook

## Phase 0 — Local prerequisites

```powershell
az --version                  # Azure CLI
databricks --version          # need a recent CLI: apps-in-bundles support
az login
az account set --subscription "<your-subscription>"
```

## Phase 1 — Azure infrastructure

```bash
# Resource group, Key Vault, CI/CD SPN, and the new public proxy SPN
bash sh/kv_spn_create.sh

# Databricks workspace (premium SKU — required for Unity Catalog)
bash sh/databricks_create.sh
```

⚠️ **`kv_spn_create.sh` generates a new vault name via `$RANDOM`.** Note the printed name and update line 3 of `pre_auth.ps1:3` to match, or authentication silently fails later.

## Phase 2 — Store the workspace URL

`databricks_create.sh` prints the URL but doesn't persist it, and `pre_auth.ps1` reads it from the vault. Your new workspace has a **different** URL than the deleted one:

```bash
WORKSPACE_URL=$(az databricks workspace show -g rg-sovereignshield -n dbw-sovereignshield --query workspaceUrl -o tsv)
az keyvault secret set --vault-name "<your-new-kv>" --name "databricks-workspace-url" --value "https://$WORKSPACE_URL"
```

## Phase 3 — Entra ID identities

```bash
bash sh/grp_users_create.sh
```

Creates five groups (including the new `sg-sovereignshield-public`) and four test users. If the users still exist from before, delete them first or the script errors.

## Phase 4 — Databricks account wiring

This is the phase that has no script, and the one most likely to bite you. `is_account_group_member()` resolves **account-level** groups — workspace-level groups will not work.

Open the **account console** (`https://accounts.azuredatabricks.net`):

1. **User management → Service principals** → add `spn-sovereignshield-cicd` by its Entra App ID (`6c0aee51-...`). Grant it **Account admin**.
2. **User management → Users** → add the four test users by UPN (`admin_lead@...`, `boc_analyst@...`, `fed_analyst@...`, `econ_researcher@...`).
3. **User management → Groups** → create five groups with names matching the SQL exactly:
   - `sg-sovereignshield-admin` — add `admin_lead` **and `spn-sovereignshield-cicd`**
   - `sg-sovereignshield-submitter-ca` — add `boc_analyst`
   - `sg-sovereignshield-submitter-us` — add `fed_analyst`
   - `sg-sovereignshield-researchers` — add `econ_researcher`
   - `sg-sovereignshield-public` — leave empty for now
4. **Workspaces → dbw-sovereignshield → Permissions** → assign all five groups plus the SPN to the workspace.

> The SPN's `sg-sovereignshield-admin` membership is not optional. The SCD2 merge reads the target table to find rows to expire; if the row filter hides them, the merge treats every row as new and silently duplicates history without raising an error.

Then confirm the catalog exists. Azure auto-creates a default catalog named after the workspace:

```sql
SHOW CATALOGS;   -- expect dbw_sovereignshield
```

If it's absent (older metastore, or UC not auto-enabled), create it and make the SPN owner before proceeding.

## Phase 5 — SQL warehouse

The portal queries through a warehouse. In the workspace: **SQL Warehouses → Create**, serverless, 2X-Small, auto-stop 10 min. Copy the **ID** from its Connection Details tab — you'll pass it to the bundle.

## Phase 6 — Deploy the bundle

```powershell
. .\sh\pre_auth.ps1        # dot-sourced — the leading dot is load-bearing
databricks bundle validate -t dev
databricks bundle deploy -t dev --var="warehouse_id=<warehouse-id>"
```

## Phase 7 — Run the pipeline

```powershell
databricks bundle run sovereignshield_sdmx_pipeline -t dev
```

Three tasks: security DDL → synthetic submissions → validation and SCD2 merge. Takes a few minutes on a cold single-node cluster. Verify:

```sql
SELECT BATCH_STATUS, IS_CURRENT, COUNT(*)
FROM dbw_sovereignshield.sovereign_shield.lbs_sdmx_history
GROUP BY 1, 2;
```

You should see `PUBLISHED`/`true` rows plus `QUARANTINE`/`false` audit rows from the revision cycle.

## Phase 8 — Deploy the portal

```powershell
databricks bundle run sovereignshield_portal -t dev
```

Then the step that has no equivalent in the old architecture:

```powershell
databricks apps get sovereignshield-portal    # note service_principal_client_id
```

**Add that service principal to `sg-sovereignshield-public` in the account console.**

This is a distinct identity from the Entra `spn-sovereignshield-public` that `kv_spn_create.sh` made. Databricks Apps mints its own managed service principal and injects *its* credentials as `DATABRICKS_CLIENT_ID`/`SECRET` — that is what anonymous requests actually run as. The Entra one is only used by the Container Apps deployment in Phase 10. Skip this and the fail-closed default returns zero rows, and the portal renders empty for every visitor.

Restart the app after changing group membership so the token cache clears.

## Phase 9 — Test from the UI

Open the app URL from `databricks apps get`. What to check, in order:

| Sign in as | Expected badge | Expected data |
|---|---|---|
| `econ_researcher` | Researcher (Published Series, Confidential Values Masked) | All countries; some values show `restricted`, and the header reports a withheld count |
| `boc_analyst` | Bank of Canada Analyst (Full Sovereign Access) | CA rows in full incl. confidential values; other countries only `PUBLISHED`+`F`. The amber "Include my quarantined batches" card appears |
| `fed_analyst` | Federal Reserve Analyst | Mirror image — **US confidential values visible, CA confidential values masked**. This is the leak I fixed; verify it |
| `admin_lead` | Platform Administrator | Everything, including quarantined batches |

Then click **Export SDMX-ML 3.0**. The download is round-tripped through the SDMx reader before it's returned, so a 422 means the payload failed validation rather than the browser choking.

Direct API check:

```powershell
curl "https://<app-url>/api/v1/health"
curl "https://<app-url>/api/v1/search?reporting_country=CA&limit=5"
```

## Phase 10 — Optional: anonymous access

```powershell
./sh/container_apps_deploy.ps1 -KeyVaultName "<your-kv>" `
    -DatabricksHost "<workspace-url-without-https>" `
    -WarehouseId "<warehouse-id>"
```

This is the only way to see a genuinely unauthenticated visitor, since a Databricks App always sits behind workspace SSO. Requires `spn-sovereignshield-public` to be added to the Databricks account and to `sg-sovereignshield-public` — same as Phase 4, but for the Entra SPN.

---

## Cost control

Since cost is why you tore it down: set the SQL warehouse auto-stop to 10 minutes, and set the app's `min-replicas` to 0 if you use Container Apps. Between sessions:

```powershell
databricks apps stop sovereignshield-portal
```

The job cluster is already spot-priced and terminates on completion. When you're done entirely, `az group delete -n rg-sovereignshield` removes everything — but re-provisioning means repeating Phases 1–4, including the manual account-console work.

**Two things most likely to fail:** the vault name in `pre_auth.ps1` not matching the newly generated one, and account groups created at workspace scope instead of account scope. Both present as "deployment worked but I see no data."

Made changes.