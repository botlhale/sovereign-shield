<#
.SYNOPSIS
    Pauses or tears down the SovereignShield workload in dependency order.

.DESCRIPTION
    Pause sets both portal hosts to their lowest-cost state and retains data.

    Workload removes policy-bound Unity Catalog objects before bundle and
    Terraform resources, preventing late schema/catalog deletion failures. It
    preserves the remote Terraform state backend and Databricks account-level
    users/groups so the environment can be rebuilt reliably.

.EXAMPLE
    ./sh/sovereignshield_down.ps1 -Mode Pause

.EXAMPLE
    ./sh/sovereignshield_down.ps1 -Mode Workload -ConfirmWorkloadDestruction

.EXAMPLE
    ./sh/sovereignshield_down.ps1 -Mode Workload -WhatIf
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [ValidateSet("Pause", "Workload")]
    [string]$Mode = "Workload",

    [switch]$ConfirmWorkloadDestruction,
    [string]$TerraformVarFile = "terraform.tfvars",
    [string]$Target = "dev",
    [string]$ResourceGroup = "rg-sovereignshield",
    [string]$WorkspaceName = "dbw-sovshield",
    [string]$DatabricksAppName = "sovereignshield-portal",
    [string]$ContainerAppName = "ca-sovereignshield-portal",
    [string]$ContainerEnvironmentName = "cae-sovereignshield"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "lib\SovereignShield.Orchestration.psm1") -Force
$repoRoot = Get-SovereignShieldRepoRoot
$terraform = Get-SovereignShieldTerraform

Push-Location $repoRoot
try {
    foreach ($command in @("az", "databricks")) {
        Assert-SovereignShieldCommand $command
    }
    Invoke-SovereignShieldNative -FilePath "az" -Arguments @("account", "show", "--output", "none") | Out-Null

    $workspaceHost = (& az databricks workspace list --resource-group $ResourceGroup `
        --query "[?name=='$WorkspaceName'].workspaceUrl | [0]" -o tsv | Out-String).Trim()
    if ($workspaceHost) { Set-SovereignShieldWorkspaceAuth -WorkspaceUrl $workspaceHost }

    if ($Mode -eq "Pause") {
        if ($PSCmdlet.ShouldProcess("SovereignShield portals", "Pause compute")) {
            if ($workspaceHost) {
                Invoke-SovereignShieldNative -FilePath "databricks" `
                    -Arguments @("apps", "stop", $DatabricksAppName) -AllowFailure | Out-Null
            }
            Invoke-SovereignShieldNative -FilePath "az" -Arguments @(
                "containerapp", "update", "--name", $ContainerAppName,
                "--resource-group", $ResourceGroup, "--min-replicas", "0", "--output", "none"
            ) -AllowFailure | Out-Null
        }
        if ($WhatIfPreference) {
            Write-Host "SovereignShield pause preview complete; no resources were changed." -ForegroundColor Green
        } else {
            Write-Host "SovereignShield is paused. Data, identities and infrastructure are retained." -ForegroundColor Green
        }
        return
    }

    if (-not $ConfirmWorkloadDestruction -and -not $WhatIfPreference) {
        throw "Workload teardown is destructive. Re-run with -ConfirmWorkloadDestruction or preview with -WhatIf."
    }

    $state = & $terraform "-chdir=$(Join-Path $repoRoot 'terraform')" state list 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Terraform state could not be read." }
    $catalogManagedByTerraform = [bool]($state | Select-String "databricks_catalog\.main")

    if ($workspaceHost -and $catalogManagedByTerraform -and $PSCmdlet.ShouldProcess("Unity Catalog data and policy objects", "Discover and delete in dependency order")) {
        $catalogName = "dbw_sovereignshield"
        $schemaNames = @("sovereign_shield", "sovereign_intake", "sovereign_submissions")
        $catalogJson = & databricks catalogs list --output json 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Could not list catalogs`n$($catalogJson | Out-String)" }
        $catalogNames = @($catalogJson | Out-String | ConvertFrom-Json | ForEach-Object { $_.name })

        if ($catalogNames -contains $catalogName) {
            $schemaJson = & databricks schemas list $catalogName --output json 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Could not list schemas in $catalogName`n$($schemaJson | Out-String)"
            }
            $existingSchemaNames = @($schemaJson | Out-String | ConvertFrom-Json | ForEach-Object { $_.name })

            # Discover live objects instead of assuming the schema encoded in DDL.
            # Tables and views must go first because they can bind policy functions.
            foreach ($kind in @("tables", "functions")) {
                foreach ($schemaName in @($schemaNames | Where-Object { $existingSchemaNames -contains $_ })) {
                    $json = & databricks $kind list $catalogName $schemaName --output json 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        throw "Could not list $kind in $catalogName.$schemaName`n$($json | Out-String)"
                    }

                    $parsedObjects = $json | Out-String | ConvertFrom-Json
                    $objects = if ($null -eq $parsedObjects) { @() } else { @($parsedObjects) }
                    foreach ($object in $objects) {
                        if (-not $object.PSObject.Properties["full_name"]) { continue }
                        Write-Host "Deleting Unity Catalog $($kind.TrimEnd('s')) $($object.full_name)" -ForegroundColor DarkGray
                        Invoke-SovereignShieldNative -FilePath "databricks" `
                            -Arguments @($kind, "delete", $object.full_name) | Out-Null
                    }
                }
            }
        }
    }

    if ($workspaceHost -and $PSCmdlet.ShouldProcess("Databricks bundle resources", "Destroy job, app and uploaded files")) {
        Invoke-SovereignShieldNative -FilePath "databricks" `
            -Arguments @("bundle", "destroy", "-t", $Target, "--auto-approve") -AllowFailure | Out-Null
    }

    $gatewayManagedByTerraform = [bool]($state | Select-String "module.dissemination_gateway")

    if ($gatewayManagedByTerraform) {
        Write-Host "Terraform-managed dissemination gateway will be removed by terraform destroy." -ForegroundColor DarkGray
    }
    else {
        if ($PSCmdlet.ShouldProcess("Script-managed Container Apps gateway", "Delete app, environment, registry and token store")) {
            Invoke-SovereignShieldNative -FilePath "az" -Arguments @(
                "containerapp", "delete", "--name", $ContainerAppName,
                "--resource-group", $ResourceGroup, "--yes"
            ) -AllowFailure | Out-Null
            Invoke-SovereignShieldNative -FilePath "az" -Arguments @(
                "containerapp", "env", "delete", "--name", $ContainerEnvironmentName,
                "--resource-group", $ResourceGroup, "--yes"
            ) -AllowFailure | Out-Null

            $registries = @(& az acr list --resource-group $ResourceGroup `
                --query "[?starts_with(name, 'acrsovereignshield')].name" -o tsv)
            foreach ($registry in $registries) {
                if ($registry) {
                    Invoke-SovereignShieldNative -FilePath "az" `
                        -Arguments @("acr", "delete", "--name", $registry, "--resource-group", $ResourceGroup, "--yes") `
                        -AllowFailure | Out-Null
                }
            }

            $tokenStores = @(& az storage account list --resource-group $ResourceGroup `
                --query "[?starts_with(name, 'stsovereignshieldauth')].name" -o tsv)
            foreach ($account in $tokenStores) {
                if ($account) {
                    Invoke-SovereignShieldNative -FilePath "az" -Arguments @(
                        "storage", "account", "delete", "--name", $account,
                        "--resource-group", $ResourceGroup, "--yes"
                    ) -AllowFailure | Out-Null
                }
            }
        }
    }

    if ($PSCmdlet.ShouldProcess("Terraform-managed SovereignShield workload", "Destroy")) {
        Invoke-SovereignShieldTerraform -Terraform $terraform -RepoRoot $repoRoot -Arguments @(
            "destroy", "-input=false", "-auto-approve", "-var-file=$TerraformVarFile",
            "-var=account_groups_ready=true", "-var=grant_tables=false",
            "-var=deploy_dissemination_gateway=false"
        ) | Out-Null
    }

    # Azure can orphan the workspace diagnostic resource after deleting the
    # Databricks workspace and its managed resource group. The generated name
    # is scoped to this workload resource group and has no Terraform owner.
    $diagnosticPrefix = "workspace-$($ResourceGroup -replace '[^A-Za-z0-9]', '')"
    $orphanedDiagnostics = @(& az resource list --resource-group $ResourceGroup `
        --resource-type "Microsoft.OperationalInsights/workspaces" `
        --query "[?starts_with(name, '$diagnosticPrefix')].id" -o tsv)
    foreach ($resourceId in $orphanedDiagnostics) {
        if ($resourceId -and $PSCmdlet.ShouldProcess($resourceId, "Delete orphaned Databricks diagnostic workspace")) {
            Invoke-SovereignShieldNative -FilePath "az" `
                -Arguments @("resource", "delete", "--ids", $resourceId) | Out-Null
        }
    }

    if ($WhatIfPreference) {
        Write-Host "`nWorkload teardown preview complete; no resources were changed." -ForegroundColor Green
        return
    }

    $remainingState = @(& $terraform "-chdir=$(Join-Path $repoRoot 'terraform')" state list 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Terraform state could not be verified after destroy." }
    if ($remainingState.Count -gt 0) {
        throw "Workload teardown left Terraform state entries behind:`n  $($remainingState -join "`n  ")"
    }

    $remainingResources = @(& az resource list --resource-group $ResourceGroup --query "[].id" -o tsv)
    if ($remainingResources.Count -gt 0) {
        throw "Workload teardown left Azure resources behind:`n  $($remainingResources -join "`n  ")"
    }

    Write-Host "`nWorkload teardown complete." -ForegroundColor Green
    Write-Host "Preserved:" -ForegroundColor Cyan
    Write-Host "  - Terraform remote-state backend"
    Write-Host "  - Databricks account-level users, groups and service principals"
    Write-Host "  - Purge-protected Key Vault tombstone until Azure retention expires"
    Write-Host "`nConfirm no workload resources remain:" -ForegroundColor Cyan
    Write-Host "  az resource list --resource-group $ResourceGroup --output table"
}
finally {
    Pop-Location
}
