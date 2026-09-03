<#
.SYNOPSIS
    Configures the GitHub repository controls the promotion workflow depends on:
    the `production` environment protection rules and the OIDC variables.

.DESCRIPTION
    Without this, `environment: production` in .github/workflows/promote.yml is
    decorative. GitHub creates an environment implicitly the first time a job
    references one, with NO protection rules attached - so the workflow appears
    to have a human gate while every merge deploys straight through.

    The rules configured here are what make the gate real:

      * required reviewers   - a person must approve before the job starts
      * prevent self-review  - the author cannot approve their own deployment,
                               which is the whole point of the review gate
      * protected branches   - deployments may only target protected branches,
                               so a feature branch cannot reach production even
                               if the workflow condition were edited

    This is separate from Terraform on purpose. Managing GitHub with the
    Terraform provider needs a personal access token, and a long-lived PAT in
    CI is exactly the stored credential the OIDC federation exists to remove.
    `gh` uses your own short-lived session instead.

    IDEMPOTENT. Re-running reports what already matches and changes only drift.

.EXAMPLE
    ./sh/github_environment_setup.ps1 -Repository botnt/sovereign-shield `
        -Reviewers botnt `
        -AzureClientId <app-id> -AzureTenantId <tenant> -AzureSubscriptionId <sub> `
        -DatabricksHost adb-1234.8.azuredatabricks.net `
        -TfStateResourceGroup rg-sovereignshield-tfstate `
        -TfStateStorageAccount stsovshieldtfstate

.NOTES
    Requires the GitHub CLI, authenticated with admin rights on the repository:
        gh auth login
        gh auth status
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Repository,

    # GitHub usernames or team slugs that may approve a production deployment.
    [string[]]$Reviewers = @(),

    [string]$EnvironmentName = "production",

    # Minutes to wait before the job starts. A non-zero value buys time to
    # cancel a deployment that was merged in error.
    [int]$WaitTimerMinutes = 0,

    # Repository variables consumed by the workflow. Left blank means "skip".
    [string]$AzureClientId = "",
    [string]$AzureTenantId = "",
    [string]$AzureSubscriptionId = "",
    [string]$DatabricksHost = "",
    [string]$TfStateResourceGroup = "",
    [string]$TfStateStorageAccount = "",
    [string]$TfStateContainer = "tfstate"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI not found. Install it, then run 'gh auth login'."
}
& gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated. Run 'gh auth login'." }

function Invoke-Gh {
    param([string[]]$Arguments, [switch]$AllowFailure)
    $out = & gh @Arguments 2>&1
    if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
        throw "gh $($Arguments -join ' ') failed:`n$out"
    }
    return $out
}

function New-TempJson($Object) {
    $path = [System.IO.Path]::GetTempFileName()
    ($Object | ConvertTo-Json -Depth 10 -Compress) | Set-Content -Path $path -Encoding utf8
    return $path
}

Write-Host "=== 1. Resolving reviewers ===" -ForegroundColor Cyan

$reviewerPayload = @()
foreach ($name in $Reviewers) {
    if ($name -match "/") {
        # org/team-slug
        $org, $slug = $name -split "/", 2
        $team = Invoke-Gh @("api", "orgs/$org/teams/$slug", "--jq", ".id") | Out-String
        $reviewerPayload += @{ type = "Team"; id = [int]$team.Trim() }
        Write-Host "  team $name"
    }
    else {
        $id = Invoke-Gh @("api", "users/$name", "--jq", ".id") | Out-String
        $reviewerPayload += @{ type = "User"; id = [int]$id.Trim() }
        Write-Host "  user $name"
    }
}

if ($reviewerPayload.Count -eq 0) {
    Write-Host "  [warn]   No reviewers supplied. The environment will exist but" -ForegroundColor Yellow
    Write-Host "           every merge deploys unattended - the gate is nominal." -ForegroundColor Yellow
}

Write-Host "`n=== 2. Environment '$EnvironmentName' ===" -ForegroundColor Cyan

$existing = Invoke-Gh @("api", "repos/$Repository/environments/$EnvironmentName") -AllowFailure
$verb = if ($LASTEXITCODE -eq 0) { "[update]" } else { "[create]" }

# Deployments are restricted to protected branches. A feature branch cannot
# reach production even if someone edits the workflow's ref condition.
$payload = @{
    wait_timer               = $WaitTimerMinutes
    prevent_self_review      = ($reviewerPayload.Count -gt 0)
    reviewers                = $reviewerPayload
    deployment_branch_policy = @{
        protected_branches     = $true
        custom_branch_policies = $false
    }
}

$file = New-TempJson $payload
try {
    Invoke-Gh @("api", "--method", "PUT", "repos/$Repository/environments/$EnvironmentName",
        "--input", $file) | Out-Null
    Write-Host "  $verb  protection rules applied" -ForegroundColor Green
}
finally { Remove-Item $file -ErrorAction SilentlyContinue }

Write-Host "`n=== 3. Repository variables ===" -ForegroundColor Cyan

$variables = [ordered]@{
    AZURE_CLIENT_ID          = $AzureClientId
    AZURE_TENANT_ID          = $AzureTenantId
    AZURE_SUBSCRIPTION_ID    = $AzureSubscriptionId
    DATABRICKS_HOST          = $DatabricksHost
    TF_STATE_RESOURCE_GROUP  = $TfStateResourceGroup
    TF_STATE_STORAGE_ACCOUNT = $TfStateStorageAccount
    TF_STATE_CONTAINER       = $TfStateContainer
}

# Variables, never secrets. Every value here is an identifier or a location;
# the credentials they point at are exchanged via OIDC at run time.
foreach ($name in $variables.Keys) {
    $value = $variables[$name]
    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Host "  [skip]   $name not supplied"
        continue
    }
    $current = Invoke-Gh @("variable", "get", $name, "--repo", $Repository) -AllowFailure | Out-String
    if ($LASTEXITCODE -eq 0 -and $current.Trim() -eq $value) {
        Write-Host "  [skip]   $name already correct"
    }
    else {
        Invoke-Gh @("variable", "set", $name, "--repo", $Repository, "--body", $value) | Out-Null
        Write-Host "  [create] $name" -ForegroundColor Green
    }
}

Write-Host "`n=== 4. Verification ===" -ForegroundColor Cyan

# Not named $env: that shadows the PowerShell environment-variable drive.
$envState = Invoke-Gh @("api", "repos/$Repository/environments/$EnvironmentName") | Out-String | ConvertFrom-Json
$reviewerRule = @($envState.protection_rules) | Where-Object { $_.type -eq "required_reviewers" }
$branchRule = $envState.deployment_branch_policy

Write-Host ("  required reviewers : {0}" -f $(if ($reviewerRule) { "yes ($($reviewerRule.reviewers.Count))" } else { "NO" }))
Write-Host ("  prevent self-review: {0}" -f $(if ($reviewerRule) { $reviewerRule.prevent_self_review } else { "n/a" }))
Write-Host ("  protected branches : {0}" -f $(if ($branchRule) { $branchRule.protected_branches } else { "NO" }))

if (-not $reviewerRule) {
    Write-Host "`n  The human gate is NOT active. Re-run with -Reviewers." -ForegroundColor Yellow
}

Write-Host "`nStill manual: protect the 'main' branch itself." -ForegroundColor DarkGray
Write-Host "  Settings > Branches > Add rule > require a pull request before merging."
Write-Host "  The environment restricts deployments to protected branches, which"
Write-Host "  means nothing at all if no branch is protected."
