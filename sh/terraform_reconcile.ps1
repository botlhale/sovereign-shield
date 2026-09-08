<#
.SYNOPSIS
    Reconciles Terraform state with what actually exists, after an interrupted
    apply or an out-of-band deletion.

.DESCRIPTION
    Terraform assumes it is the only writer. When that assumption breaks - a
    destroy is interrupted, a resource group is deleted in the portal, an apply
    fails half-way - state and reality diverge in one of two directions:

      * State holds a resource that no longer exists. Refresh fails, or the plan
        tries to update something absent.
        Fix: terraform state rm.

      * A resource exists that state does not know about. Apply fails with
        "already exists - to be managed via Terraform this resource needs to be
        imported".
        Fix: terraform import.

    Neither operation touches a cloud resource. This script only ever changes
    Terraform's opinion.

    SCOPE IS THE THING PEOPLE GET WRONG. Unity Catalog objects live in the
    METASTORE, which is account-level, so a catalog, storage credential or
    external location outlives the workspace that created it. Cluster policies,
    secret scopes and SQL warehouses are workspace-scoped and die with it.
    Deleting a workspace therefore orphans the first group and destroys the
    second, and the recovery differs accordingly.

    Key Vault secrets return from the dead for a different reason: the vault is
    created with purge protection, so deleting it soft-deletes it, and
    recover_soft_deleted_key_vaults brings it back complete with every secret.

.PARAMETER ResourceGroup
    Resource group holding the platform. Used to discover the Key Vault.

.PARAMETER Catalog
    Unity Catalog catalog name, matching var.catalog_name.

.PARAMETER WhatIf
    Report what would change without touching state.

.EXAMPLE
    ./sh/terraform_reconcile.ps1 -WhatIf
    ./sh/terraform_reconcile.ps1

.NOTES
    Run from the repository root, with terraform already initialised.
    Safe to re-run: every action is skipped when already correct.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ResourceGroup = "rg-sovereignshield",
    [string]$Catalog = "dbw_sovereignshield",
    [string]$TerraformDir = "terraform"
)

Set-StrictMode -Version Latest

# A native command's stderr becomes ErrorRecords under 2>&1, and a 'Stop'
# preference would terminate on the first one. Probing for absence is the whole
# job here, so decisions are made on exit codes instead.
$ErrorActionPreference = "Continue"

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $out = & $Exe @Arguments 2>&1 | Out-String
    return [pscustomobject]@{ Output = $out.Trim(); ExitCode = $LASTEXITCODE }
}

function Test-InState {
    param([string]$Address, [string[]]$StateList)
    return $StateList -contains $Address
}

if (-not (Test-Path $TerraformDir)) {
    throw "Directory '$TerraformDir' not found. Run this from the repository root."
}
Push-Location $TerraformDir

try {
    Write-Host "=== 1. Reading state ===" -ForegroundColor Cyan

    $stateResult = Invoke-Native terraform @("state", "list")
    if ($stateResult.ExitCode -ne 0) {
        throw "terraform state list failed. Is the backend initialised?`n$($stateResult.Output)"
    }
    $stateList = $stateResult.Output -split "`r?`n" | Where-Object { $_ -ne "" }
    Write-Host ("  {0} resource(s) tracked" -f $stateList.Count)

    # -----------------------------------------------------------------------
    # Metastore-scoped Unity Catalog objects.
    #
    # These survive workspace deletion. Removing them from state - the correct
    # move for workspace-scoped objects - orphans them, and the next apply fails
    # on "already exists".
    # -----------------------------------------------------------------------
    Write-Host "`n=== 2. Unity Catalog objects (metastore-scoped) ===" -ForegroundColor Cyan

    $ucObjects = @(
        @{ Address = "module.databricks_workspace.databricks_storage_credential.main"; Id = "sc-sovereignshield" }
        @{ Address = "module.databricks_workspace.databricks_external_location.main"; Id = "el-sovereignshield" }
        @{ Address = "module.unity_catalog_governance.databricks_catalog.main"; Id = $Catalog }
    )

    foreach ($obj in $ucObjects) {
        if (Test-InState -Address $obj.Address -StateList $stateList) {
            Write-Host ("  [skip]   {0} already tracked" -f $obj.Id)
            continue
        }

        if ($PSCmdlet.ShouldProcess($obj.Address, "terraform import '$($obj.Id)'")) {
            $result = Invoke-Native terraform @("import", $obj.Address, $obj.Id)
            if ($result.ExitCode -eq 0) {
                Write-Host ("  [import] {0}" -f $obj.Id) -ForegroundColor Green
            }
            elseif ($result.Output -match "does not exist|not found|NOT_FOUND|RESOURCE_DOES_NOT_EXIST") {
                # Nothing to adopt. The next apply creates it.
                Write-Host ("  [absent] {0} - will be created" -f $obj.Id)
            }
            else {
                Write-Host ("  [warn]   {0} import failed:" -f $obj.Id) -ForegroundColor Yellow
                $firstLines = ($result.Output -split "`r?`n" | Select-Object -First 3) -join " "
                Write-Host ("           {0}" -f $firstLines)
            }
        }
    }

    # -----------------------------------------------------------------------
    # Key Vault secrets recovered with a soft-deleted vault.
    #
    # The versioned secret id is required for import, and it changes on every
    # write, so it has to be discovered rather than hardcoded.
    # -----------------------------------------------------------------------
    Write-Host "`n=== 3. Key Vault secrets ===" -ForegroundColor Cyan

    # az is a .cmd shim on Windows and mangles a JMESPath filter containing
    # quotes, so the match is done here instead.
    $vaultResult = Invoke-Native az @(
        "keyvault", "list", "-g", $ResourceGroup, "--query", "[].name", "-o", "tsv"
    )
    $vault = ($vaultResult.Output -split "`r?`n" |
        Where-Object { $_ -like "kv-sovereignshield*" } |
        Select-Object -First 1)

    if (-not $vault) {
        Write-Host "  [skip]   no kv-sovereignshield* vault in $ResourceGroup"
    }
    else {
        Write-Host "  vault: $vault"

        $secrets = @(
            @{ Address = "module.databricks_workspace.azurerm_key_vault_secret.workspace_url"; Name = "databricks-workspace-url" }
            @{ Address = "module.identity.azurerm_key_vault_secret.public_spn_client_id"; Name = "public-spn-client-id" }
            @{ Address = "module.identity.azurerm_key_vault_secret.public_spn_client_secret"; Name = "public-spn-client-secret" }
            @{ Address = "module.identity.azurerm_key_vault_secret.tenant_id"; Name = "spn-tenant-id" }
        )

        foreach ($secret in $secrets) {
            if (Test-InState -Address $secret.Address -StateList $stateList) {
                Write-Host ("  [skip]   {0} already tracked" -f $secret.Name)
                continue
            }

            # Only the id is read. The secret value is never retrieved, printed
            # or passed on a command line.
            $idResult = Invoke-Native az @(
                "keyvault", "secret", "show",
                "--vault-name", $vault, "--name", $secret.Name,
                "--query", "id", "-o", "tsv"
            )

            if ($idResult.ExitCode -ne 0 -or -not $idResult.Output) {
                Write-Host ("  [absent] {0} - will be created" -f $secret.Name)
                continue
            }

            if ($PSCmdlet.ShouldProcess($secret.Address, "terraform import")) {
                $result = Invoke-Native terraform @("import", $secret.Address, $idResult.Output)
                if ($result.ExitCode -eq 0) {
                    Write-Host ("  [import] {0}" -f $secret.Name) -ForegroundColor Green
                }
                else {
                    Write-Host ("  [warn]   {0} import failed" -f $secret.Name) -ForegroundColor Yellow
                }
            }
        }
    }

    # -----------------------------------------------------------------------
    # Workspace-scoped objects that state still claims exist.
    #
    # Only prune when the workspace itself is gone. Pruning while it is alive
    # would orphan live objects and duplicate them on the next apply.
    # -----------------------------------------------------------------------
    Write-Host "`n=== 4. Workspace-scoped objects ===" -ForegroundColor Cyan

    $wsResult = Invoke-Native az @(
        "databricks", "workspace", "list", "-g", $ResourceGroup,
        "--query", "[].name", "-o", "tsv"
    )
    $workspaceAlive = ($wsResult.ExitCode -eq 0 -and $wsResult.Output -ne "")

    if ($workspaceAlive) {
        Write-Host "  workspace present - nothing to prune"
    }
    else {
        Write-Host "  no workspace in $ResourceGroup; these objects cannot exist" -ForegroundColor Yellow

        $workspaceScoped = @(
            "module.databricks_workspace.databricks_cluster_policy.ingestion"
            "module.databricks_workspace.databricks_secret_scope.key_vault"
            "module.unity_catalog_governance.databricks_sql_endpoint.dissemination"
        )

        foreach ($address in $workspaceScoped) {
            if (-not (Test-InState -Address $address -StateList $stateList)) {
                Write-Host ("  [skip]   {0} not tracked" -f $address.Split('.')[-1])
                continue
            }
            if ($PSCmdlet.ShouldProcess($address, "terraform state rm")) {
                $result = Invoke-Native terraform @("state", "rm", $address)
                if ($result.ExitCode -eq 0) {
                    Write-Host ("  [forget] {0}" -f $address.Split('.')[-1]) -ForegroundColor Green
                }
            }
        }
    }

    Write-Host "`n=== Done ===" -ForegroundColor Cyan
    Write-Host "  terraform plan -out=tfplan"
    Write-Host "  terraform apply tfplan"
    Write-Host "`n  Nothing in Azure or Databricks was created, changed or deleted." -ForegroundColor DarkGray
}
finally {
    Pop-Location
}
