# Rebuild & test runbook

Every script here is **idempotent**: it checks before it creates, prints
`[skip]` for what already exists and `[create]` for what it adds. Since your
Entra users, groups and service principals survived the workspace teardown,
most of Phases 1–3 will report `[skip]` and only fill in the gaps.

Credentials are the one thing never recreated silently. If a service principal
exists and its secret is already in Key Vault, the scripts leave it alone —
resetting it would invalidate the copy the pipeline is using and surface later
as an opaque 401. Use `sh/kv_spn_remediation.sh` when you actually want to rotate.

## Phase 0 — Local prerequisites

```powershell
az --version                  # Azure CLI
databricks --version          # v1.10+ for apps-in-bundles
az login
az account set --subscription "<your-subscription>"
```

## Phase 1 — Azure infrastructure

```bash
bash sh/kv_spn_create.sh
```

Reuses the resource group, discovers your existing `kv-sovereignshield-*` vault
by prefix, and reuses both service principals. It only mints a credential when
the matching vault secret is missing.

The vault name is no longer hardcoded anywhere — `pre_auth.ps1` discovers it the
same way, so there is nothing to edit by hand.

```bash
bash sh/databricks_create.sh
```

Creates the workspace only if absent, then writes `databricks-workspace-url` to
Key Vault. **This is the step that matters most after a teardown:** your rebuilt
workspace has a different URL, and a stale secret authenticates against a
workspace that no longer exists.

> Phase 2 from the earlier version of this runbook is gone — storing the
> workspace URL is now part of `databricks_create.sh`.

## Phase 2 — Entra ID identities

```bash
bash sh/grp_users_create.sh
```

Ensures five groups and four users exist, and that memberships are correct. An
existing user's password is never reset. This also adds `spn-sovereignshield-cicd`
to `sg-sovereignshield-admin`, which used to be a manual step.

> That membership is not optional. The SCD2 merge reads the history table to
> find rows to expire; if the row filter hid them, the merge would treat every
> row as new and silently duplicate history without raising an error.

If you ran Phase 1 before the groups existed, re-run `kv_spn_create.sh` now — it
will add the proxy service principal to `sg-sovereignshield-public` and skip
everything else.

## Phase 3 — Databricks account wiring

Previously the manual account-console phase, and the most common cause of
"the deploy worked but I see no data". Now scripted:

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

Azure auto-creates a default catalog named after the workspace. If it's absent,
create it and make the SPN owner before proceeding. The `sovereign_shield`
schema is created by the DDL itself — that was a genuine gap, since the old
script did `USE SCHEMA` on a schema it never created.

## Phase 4 — SQL warehouse

The portal queries through a warehouse. In the workspace: **SQL Warehouses →
Create**, serverless, 2X-Small, auto-stop 10 min. Copy the **ID** from its
Connection Details tab.

If you already have one, reuse it — nothing here is workspace-version specific.

## Phase 5 — Deploy the bundle

```powershell
. .\sh\pre_auth.ps1        # dot-sourced — the leading dot is load-bearing
databricks bundle validate -t dev
databricks bundle deploy -t dev --var="warehouse_id=<warehouse-id>"
```

`pre_auth.ps1` now discovers the vault and prints the workspace it resolved, so
a stale URL is visible immediately rather than surfacing as a deploy failure.

## Phase 6 — Run the pipeline

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

## Phase 7 — Deploy the portal

```powershell
databricks bundle run sovereignshield_portal -t dev
./sh/databricks_account_setup.ps1 -AccountId "<your-account-id>" -AppName sovereignshield-portal
```

The second command is the one that used to be a manual account-console step. Re-running the same script with `-AppName` resolves the app's managed service principal and adds it to `sg-sovereignshield-public`, skipping everything it already did.

**Why a second identity:** Databricks Apps mints its *own* managed service principal and injects those credentials as `DATABRICKS_CLIENT_ID`/`SECRET`. That — not the Entra `spn-sovereignshield-public` — is what anonymous requests actually run as. The Entra one is only used by the Container Apps deployment in Phase 9. Skip this and the fail-closed default returns zero rows, and the portal renders empty for every visitor.

Restart the app afterwards so it picks up the new membership.

## Phase 8 — Test from the UI

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

## Phase 9 — Optional: anonymous access

```powershell
./sh/container_apps_deploy.ps1 -KeyVaultName "<your-kv>" `
    -DatabricksHost "<workspace-url-without-https>" `
    -WarehouseId "<warehouse-id>"
```

Also idempotent: it discovers an existing `acrsovereignshield*` registry, reuses the Container Apps environment, and `update`s the app rather than failing if it already exists. The image is always rebuilt, since shipping new code is the point of re-running.

This is the only way to see a genuinely unauthenticated visitor, since a Databricks App always sits behind workspace SSO. Requires `spn-sovereignshield-public` in the Databricks account and in `sg-sovereignshield-public` — handled by Phase 3.

---

## What re-running does

| Script | Re-run behaviour |
|---|---|
| `kv_spn_create.sh` | Reuses RG, vault, both SPNs. Mints a credential **only** if its vault secret is missing |
| `databricks_create.sh` | Reuses the workspace; always refreshes `databricks-workspace-url` if it changed |
| `grp_users_create.sh` | Reuses groups and users; never resets an existing password |
| `databricks_account_setup.ps1` | Reuses account identities; adds missing memberships and workspace assignments |
| `container_apps_deploy.ps1` | Reuses registry, environment and app; always rebuilds and rolls out the image |
| `kv_spn_remediation.sh` | **Destructive by design** — deletes the app registration and rotates credentials |

---

## Cost control

Since cost is why you tore it down: set the SQL warehouse auto-stop to 10 minutes, and set the app's `min-replicas` to 0 if you use Container Apps. Between sessions:

```powershell
databricks apps stop sovereignshield-portal
```

The job cluster is already spot-priced and terminates on completion. When you're done entirely, `az group delete -n rg-sovereignshield` removes everything — but that also deletes the Key Vault and both service principals' stored secrets, so the next rebuild mints fresh credentials. Deleting only the **workspace** is the cheaper teardown: identities and vault survive, and Phases 1–3 become near-no-ops.

**Most likely failure now:** account groups that exist at workspace scope rather than account scope, from an earlier manual attempt. They look identical in the UI. If the portal renders empty for a persona that should see rows, check that first — `databricks account groups list --filter "displayName eq 'sg-sovereignshield-public'"` should return a match.

Made changes.