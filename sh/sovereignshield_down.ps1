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

    $workspaceHost = (& az databricks workspace show --name $WorkspaceName `
        --resource-group $ResourceGroup --query workspaceUrl -o tsv 2>$null | Out-String).Trim()
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

    if (-not $workspaceHost) {
        throw "Workspace '$WorkspaceName' was not found. Run sh/terraform_reconcile.ps1 before teardown if state and Azure have drifted."
    }

    if ($PSCmdlet.ShouldProcess("Unity Catalog data and policy objects", "Delete in dependency order")) {
        $published = "dbw_sovereignshield.sovereign_shield"
        $intake = "dbw_sovereignshield.sovereign_intake"
        foreach ($object in @(
            @{ Kind = "tables"; Name = "$published.v_agg_sdmx_published" },
            @{ Kind = "tables"; Name = "$published.agg_sdmx_history" },
            @{ Kind = "tables"; Name = "$intake.lbs_micro_transactions" },
            @{ Kind = "functions"; Name = "$published.fn_ddm_obs_conf_mask" },
            @{ Kind = "functions"; Name = "$published.fn_rls_multi_persona_lock" },
            @{ Kind = "functions"; Name = "$intake.fn_rls_micro_country_lock" }
        )) {
            Invoke-SovereignShieldNative -FilePath "databricks" `
                -Arguments @($object.Kind, "delete", $object.Name) -AllowFailure | Out-Null
        }
    }

    if ($PSCmdlet.ShouldProcess("Databricks bundle resources", "Destroy job, app and uploaded files")) {
        Invoke-SovereignShieldNative -FilePath "databricks" `
            -Arguments @("bundle", "destroy", "-t", $Target, "--auto-approve") -AllowFailure | Out-Null
    }

    $state = & $terraform "-chdir=$(Join-Path $repoRoot 'terraform')" state list 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Terraform state could not be read." }
    $gatewayManagedByTerraform = [bool]($state | Select-String "module.dissemination_gateway")

    if ($gatewayManagedByTerraform) {
        if ($PSCmdlet.ShouldProcess("Terraform-managed dissemination gateway", "Disable gateway module")) {
            Invoke-SovereignShieldTerraformApply -Terraform $terraform -RepoRoot $repoRoot `
                -VarFile $TerraformVarFile -Variables @(
                    "account_groups_ready=true", "grant_tables=false",
                    "deploy_dissemination_gateway=false"
                )
        }
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

    if ($PSCmdlet.ShouldProcess("Terraform table grants", "Remove before dropping tables and catalog")) {
        Invoke-SovereignShieldTerraformApply -Terraform $terraform -RepoRoot $repoRoot `
            -VarFile $TerraformVarFile -Variables @(
                "account_groups_ready=true", "grant_tables=false",
                "deploy_dissemination_gateway=false"
            )
    }

    if ($PSCmdlet.ShouldProcess("Terraform-managed SovereignShield workload", "Destroy")) {
        Invoke-SovereignShieldTerraform -Terraform $terraform -RepoRoot $repoRoot -Arguments @(
            "destroy", "-input=false", "-auto-approve", "-var-file=$TerraformVarFile",
            "-var=account_groups_ready=true", "-var=grant_tables=false",
            "-var=deploy_dissemination_gateway=false"
        ) | Out-Null
    }

    if ($WhatIfPreference) {
        Write-Host "`nWorkload teardown preview complete; no resources were changed." -ForegroundColor Green
        return
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
