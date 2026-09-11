<#
.SYNOPSIS
    Provisions and starts the complete SovereignShield reference environment.

.DESCRIPTION
    Orchestrates the Terraform deployment path from existing local
    terraform/terraform.tfvars and terraform/backend.hcl through account wiring,
    Asset Bundle deployment, ingestion, grants, both portal hosts and live
    readiness checks.

    Human Entra users must already exist. The script validates them but never
    creates users or handles passwords.

.EXAMPLE
    ./sh/sovereignshield_up.ps1 `
        -AccountId "<databricks-account-guid>" `
        -TenantDomain "example.onmicrosoft.com"

.EXAMPLE
    # Resume after a completed pipeline if a later cloud operation timed out.
    ./sh/sovereignshield_up.ps1 -AccountId "<guid>" `
        -TenantDomain "example.onmicrosoft.com" -StartAtStage 5
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')]
    [string]$AccountId,

    [Parameter(Mandatory = $true)]
    [string]$TenantDomain,

    [string]$TerraformVarFile = "terraform.tfvars",
    [string]$TerraformBackendConfig = "backend.hcl",
    [string]$Target = "dev",
    [string]$ResourceGroup = "rg-sovereignshield",
    [string]$WorkspaceName = "dbw-sovshield",
    [string]$AppName = "sovereignshield-portal",
    [string]$Location = "canadacentral",

    [ValidateRange(0, 8)]
    [int]$StartAtStage = 0,

    [ValidateRange(0, 8)]
    [int]$StopAfterStage = 8,

    [switch]$SkipTests,
    [switch]$ConfigureGitHub,
    [string]$GitHubRepository = "",
    [string[]]$GitHubReviewers = @(),
    [bool]$EnableEntraSignIn = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "lib\SovereignShield.Orchestration.psm1") -Force
$repoRoot = Get-SovereignShieldRepoRoot
$terraform = Get-SovereignShieldTerraform
$startedAt = Get-Date
$stageTimings = [ordered]@{}

if ($StartAtStage -gt $StopAfterStage) {
    throw "StartAtStage cannot be greater than StopAfterStage."
}

Push-Location $repoRoot
try {
    function Invoke-Stage {
        param(
            [int]$Number,
            [string]$Name,
            [scriptblock]$Action
        )
        if ($Number -lt $StartAtStage -or $Number -gt $StopAfterStage) {
            Write-Host "`n[$Number/8] SKIP $Name" -ForegroundColor DarkGray
            return
        }

        Write-Host "`n[$Number/8] $Name" -ForegroundColor Cyan
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        & $Action
        $timer.Stop()
        $stageTimings[$Name] = $timer.Elapsed
        Write-Host "[$Number/8] COMPLETE in $([math]::Round($timer.Elapsed.TotalMinutes, 1)) minute(s)" -ForegroundColor Green
    }

    function Get-BackendValue {
        param([string]$Name)
        $path = Join-Path $repoRoot "terraform\$TerraformBackendConfig"
        $pattern = '^\s*{0}\s*=\s*"([^"]+)"' -f [regex]::Escape($Name)
        $match = Select-String -Path $path -Pattern $pattern | Select-Object -First 1
        return if ($match) { $match.Matches[0].Groups[1].Value } else { "" }
    }

    Invoke-Stage 0 "Preflight and offline verification" {
        foreach ($command in @("az", "databricks", "git")) {
            Assert-SovereignShieldCommand $command
        }
        if (-not $SkipTests) { Assert-SovereignShieldCommand ".\.venv\Scripts\python.exe" }

        foreach ($relativePath in @(
            "terraform\$TerraformVarFile",
            "terraform\$TerraformBackendConfig"
        )) {
            if (-not (Test-Path (Join-Path $repoRoot $relativePath))) {
                throw "Missing $relativePath. Copy and complete its .example file first."
            }
        }

        Invoke-SovereignShieldNative -FilePath "az" -Arguments @("account", "show", "--output", "none") | Out-Null
        foreach ($provider in @(
            "Microsoft.Databricks", "Microsoft.App", "Microsoft.OperationalInsights",
            "Microsoft.KeyVault", "Microsoft.Storage", "Microsoft.ManagedIdentity"
        )) {
            Invoke-SovereignShieldNative -FilePath "az" `
                -Arguments @("provider", "register", "--namespace", $provider, "--wait", "--output", "none") | Out-Null
        }

        Test-SovereignShieldEntraUsers -TenantDomain $TenantDomain
        if (-not $SkipTests) {
            Invoke-SovereignShieldNative -FilePath ".\.venv\Scripts\python.exe" `
                -Arguments @("-m", "pytest", "-q") | Out-Null
        }
    }
    if ($StopAfterStage -eq 0) { return }

    Invoke-Stage 1 "Terraform foundation" {
        Invoke-SovereignShieldTerraform -Terraform $terraform -RepoRoot $repoRoot `
            -Arguments @("init", "-input=false", "-backend-config=$TerraformBackendConfig") | Out-Null
        Invoke-SovereignShieldTerraform -Terraform $terraform -RepoRoot $repoRoot `
            -Arguments @("validate") | Out-Null
        Invoke-SovereignShieldTerraformApply -Terraform $terraform -RepoRoot $repoRoot `
            -VarFile $TerraformVarFile -Variables @(
                "account_groups_ready=false",
                "grant_tables=false",
                "deploy_dissemination_gateway=false"
            )
    }

    $workspaceUrl = Get-SovereignShieldTerraformOutput -Terraform $terraform -RepoRoot $repoRoot -Name "workspace_url"
    $warehouseId = Get-SovereignShieldTerraformOutput -Terraform $terraform -RepoRoot $repoRoot -Name "sql_warehouse_id"
    $submissionVolume = Get-SovereignShieldTerraformOutput -Terraform $terraform -RepoRoot $repoRoot -Name "submission_volume_path"
    $keyVaultName = Get-SovereignShieldTerraformOutput -Terraform $terraform -RepoRoot $repoRoot -Name "key_vault_name"
    Set-SovereignShieldWorkspaceAuth -WorkspaceUrl $workspaceUrl
    if ($StopAfterStage -eq 1) { return }

    Invoke-Stage 2 "Databricks account identities and persona grants" {
        & (Join-Path $repoRoot "sh\databricks_account_setup.ps1") `
            -AccountId $AccountId -ResourceGroup $ResourceGroup `
            -WorkspaceName $WorkspaceName -TenantDomain $TenantDomain
        Invoke-SovereignShieldTerraformApply -Terraform $terraform -RepoRoot $repoRoot `
            -VarFile $TerraformVarFile -Variables @(
                "account_groups_ready=true",
                "grant_tables=false",
                "deploy_dissemination_gateway=false"
            )
    }

    Invoke-Stage 3 "Databricks Asset Bundle deployment" {
        Invoke-SovereignShieldNative -FilePath "databricks" `
            -Arguments @("bundle", "validate", "-t", $Target, "--var=warehouse_id=$warehouseId", "--var=submission_volume=$submissionVolume") | Out-Null
        Invoke-SovereignShieldNative -FilePath "databricks" `
            -Arguments @("bundle", "deploy", "-t", $Target, "--var=warehouse_id=$warehouseId", "--var=submission_volume=$submissionVolume") | Out-Null
    }

    Invoke-Stage 4 "SDMx generation, validation and SCD2 pipeline" {
        Invoke-SovereignShieldNative -FilePath "databricks" `
            -Arguments @("bundle", "run", "sovereignshield_sdmx_pipeline", "-t", $Target) | Out-Null
    }

    Invoke-Stage 5 "Table and policy-function grants" {
        Invoke-SovereignShieldTerraformApply -Terraform $terraform -RepoRoot $repoRoot `
            -VarFile $TerraformVarFile -Variables @(
                "account_groups_ready=true",
                "grant_tables=true",
                "deploy_dissemination_gateway=false"
            )
    }

    Invoke-Stage 6 "Databricks App activation" {
        Invoke-SovereignShieldNative -FilePath "databricks" `
            -Arguments @("bundle", "run", "sovereignshield_portal", "-t", $Target, "--var=warehouse_id=$warehouseId") | Out-Null
        & (Join-Path $repoRoot "sh\databricks_account_setup.ps1") `
            -AccountId $AccountId -ResourceGroup $ResourceGroup -WorkspaceName $WorkspaceName `
            -TenantDomain $TenantDomain -AppName $AppName
        Invoke-SovereignShieldNative -FilePath "databricks" `
            -Arguments @("bundle", "run", "sovereignshield_portal", "-t", $Target, "--var=warehouse_id=$warehouseId") | Out-Null
    }

    Invoke-Stage 7 "Azure Container Apps public and signed-in gateway" {
        $containerArguments = @{
            KeyVaultName  = $keyVaultName
            DatabricksHost = $workspaceUrl.Replace("https://", "")
            WarehouseId   = $warehouseId
            ResourceGroup = $ResourceGroup
            Location      = $Location
        }
        if ($EnableEntraSignIn) { $containerArguments["EnableEntraSignIn"] = $true }
        & (Join-Path $repoRoot "sh\container_apps_deploy.ps1") @containerArguments
    }

    Invoke-Stage 8 "Readiness checks and deployment summary" {
        $app = (& databricks apps get $AppName --output json | Out-String | ConvertFrom-Json)
        if ($LASTEXITCODE -ne 0 -or $app.app_status.state -ne "RUNNING") {
            throw "Databricks App '$AppName' is not running."
        }

        $containerFqdn = (& az containerapp show --name "ca-sovereignshield-portal" `
            --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($containerFqdn)) {
            throw "Container Apps portal FQDN is unavailable."
        }
        $health = Invoke-RestMethod "https://$containerFqdn/api/v1/health"
        if ($health.status -ne "ok") { throw "Container Apps health check is not OK." }

        if ($ConfigureGitHub) {
            if ([string]::IsNullOrWhiteSpace($GitHubRepository)) {
                throw "-GitHubRepository is required with -ConfigureGitHub."
            }
            $backendResourceGroup = Get-BackendValue "resource_group_name"
            $backendStorageAccount = Get-BackendValue "storage_account_name"
            $subscriptionId = (& az account show --query id -o tsv | Out-String).Trim()
            $tenantId = (& az account show --query tenantId -o tsv | Out-String).Trim()
            $cicdClientId = Get-SovereignShieldTerraformOutput -Terraform $terraform -RepoRoot $repoRoot -Name "cicd_client_id"
            & (Join-Path $repoRoot "sh\github_environment_setup.ps1") `
                -Repository $GitHubRepository -Reviewers $GitHubReviewers `
                -AzureClientId $cicdClientId -AzureTenantId $tenantId `
                -AzureSubscriptionId $subscriptionId `
                -DatabricksHost $workspaceUrl.Replace("https://", "") `
                -TfStateResourceGroup $backendResourceGroup `
                -TfStateStorageAccount $backendStorageAccount
        }

        Write-Host "`nSovereignShield is ready." -ForegroundColor Green
        Write-Host "  Databricks App : $($app.url)"
        Write-Host "  Public portal  : https://$containerFqdn"
        Write-Host "  Warehouse      : $warehouseId"
        Write-Host "  Submission root: $submissionVolume"
        Write-Host "  Elapsed         : $([math]::Round(((Get-Date) - $startedAt).TotalMinutes, 1)) minute(s)"
    }

    Write-Host "`nStage timings" -ForegroundColor Cyan
    $stageTimings.GetEnumerator() | ForEach-Object {
        "  {0,-55} {1,6:N1} min" -f $_.Key, $_.Value.TotalMinutes
    }
}
finally {
    Pop-Location
}
