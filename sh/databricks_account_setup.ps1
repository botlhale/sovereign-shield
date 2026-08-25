<#
.SYNOPSIS
    Idempotently wires the Databricks ACCOUNT layer: users, service principals,
    groups, memberships, and workspace assignment.

.DESCRIPTION
    This is the phase that used to be manual, and the one most likely to be the
    reason "the deploy worked but I see no data".

    `is_account_group_member()` resolves ACCOUNT-level groups. Groups created at
    workspace scope look identical in the UI and will never match, so the row
    filter falls through to its fail-closed default and returns zero rows.

    Deleting an Azure Databricks workspace does NOT delete account-level
    identities. After a teardown the users, service principals and groups are
    usually still present and only the workspace assignment is missing - so
    every object here is checked before it is created.

    Authentication: uses your interactive `az login` identity by default,
    because an Entra Global Administrator is automatically a Databricks account
    admin. That avoids the bootstrap problem where the CI/CD service principal
    cannot grant itself the access it needs. ARM_* variables set by
    pre_auth.ps1 are suppressed for the duration so they cannot shadow it.

.EXAMPLE
    ./sh/databricks_account_setup.ps1 -AccountId "12345678-90ab-cdef-1234-567890abcdef"

.EXAMPLE
    # Re-run after the app is deployed to grant it the public tier
    ./sh/databricks_account_setup.ps1 -AccountId "..." -AppName sovereignshield-portal

.NOTES
    Find the account id at https://accounts.azuredatabricks.net (top-right menu).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AccountId,
    [string]$ResourceGroup = "rg-sovereignshield",
    [string]$WorkspaceName = "dbw-sovereignshield",
    [string]$TenantDomain = "13668754CANADAINC.onmicrosoft.com",
    [string]$AppName = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$GROUPS = @(
    "sg-sovereignshield-admin",
    "sg-sovereignshield-submitter-ca",
    "sg-sovereignshield-submitter-us",
    "sg-sovereignshield-researchers",
    "sg-sovereignshield-public"
)

$USERS = @(
    @{ Prefix = "admin_lead";      Display = "Admin Lead";      Group = "sg-sovereignshield-admin" },
    @{ Prefix = "boc_analyst";     Display = "BOC Analyst";     Group = "sg-sovereignshield-submitter-ca" },
    @{ Prefix = "fed_analyst";     Display = "Fed Analyst";     Group = "sg-sovereignshield-submitter-us" },
    @{ Prefix = "econ_researcher"; Display = "Econ Researcher"; Group = "sg-sovereignshield-researchers" }
)

# Entra app registrations that must exist as Databricks account service principals.
$SERVICE_PRINCIPALS = @(
    @{ Name = "spn-sovereignshield-cicd";   Group = "sg-sovereignshield-admin" },
    @{ Name = "spn-sovereignshield-public"; Group = "sg-sovereignshield-public" }
)

# ---------------------------------------------------------------------
# Session setup
# ---------------------------------------------------------------------

# Resolved against the WORKSPACE, before the host is switched to the account API.
$appClientId = ""
if ($AppName) {
    Write-Host "Resolving the managed service principal for app '$AppName'..." -ForegroundColor Cyan
    $appJson = & databricks apps get $AppName -o json 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read app '$AppName'. Deploy it first, and dot-source sh/pre_auth.ps1 for workspace credentials.`n$appJson"
    }
    $appClientId = ($appJson | Out-String | ConvertFrom-Json).service_principal_client_id
}

$saved = @{
    Host      = $env:DATABRICKS_HOST
    AccountId = $env:DATABRICKS_ACCOUNT_ID
    ClientId  = $env:ARM_CLIENT_ID
    Secret    = $env:ARM_CLIENT_SECRET
    Tenant    = $env:ARM_TENANT_ID
}

$env:DATABRICKS_HOST = "https://accounts.azuredatabricks.net"
$env:DATABRICKS_ACCOUNT_ID = $AccountId
$env:ARM_CLIENT_ID = $null
$env:ARM_CLIENT_SECRET = $null
$env:ARM_TENANT_ID = $null

function Invoke-Db {
    param([string[]]$Arguments)
    $raw = & databricks @Arguments -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "databricks $($Arguments -join ' ') failed: $raw" }
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | Out-String | ConvertFrom-Json)
}

function Get-Resources($response) {
    if ($null -eq $response) { return @() }
    # The CLI returns a bare array on some versions and a SCIM envelope on others.
    if ($response.PSObject.Properties.Name -contains "Resources") { return @($response.Resources) }
    return @($response)
}

function New-TempJson($object) {
    $path = [System.IO.Path]::GetTempFileName()
    ($object | ConvertTo-Json -Depth 10 -Compress) | Set-Content -Path $path -Encoding utf8
    return $path
}

function Add-GroupMember {
    param([string]$GroupId, [string]$GroupName, [string]$PrincipalId, [string]$Label)

    $group = Invoke-Db @("account", "groups", "get", $GroupId)
    $existing = @()
    if ($group.PSObject.Properties.Name -contains "members" -and $group.members) {
        $existing = @($group.members | ForEach-Object { $_.value })
    }
    if ($existing -contains $PrincipalId) {
        Write-Host "  [skip]   $Label already in $GroupName"
        return
    }

    Write-Host "  [create] Adding $Label to $GroupName" -ForegroundColor Green
    $payload = @{
        schemas    = @("urn:ietf:params:scim:api:messages:2.0:PatchOp")
        Operations = @(@{ op = "add"; path = "members"; value = @(@{ value = $PrincipalId }) })
    }
    $file = New-TempJson $payload
    try { Invoke-Db @("account", "groups", "patch", $GroupId, "--json", "@$file") | Out-Null }
    finally { Remove-Item $file -ErrorAction SilentlyContinue }
}

try {
    Write-Host "=== 1. Account groups ===" -ForegroundColor Cyan
    $groupIds = @{}
    foreach ($name in $GROUPS) {
        $found = Get-Resources (Invoke-Db @("account", "groups", "list", "--filter", "displayName eq '$name'"))
        if ($found.Count -gt 0) {
            Write-Host "  [skip]   Group $name exists"
            $groupIds[$name] = $found[0].id
        }
        else {
            Write-Host "  [create] Group $name" -ForegroundColor Green
            $file = New-TempJson @{ displayName = $name }
            try { $groupIds[$name] = (Invoke-Db @("account", "groups", "create", "--json", "@$file")).id }
            finally { Remove-Item $file -ErrorAction SilentlyContinue }
        }
    }

    Write-Host "`n=== 2. Account users ===" -ForegroundColor Cyan
    foreach ($user in $USERS) {
        $upn = "$($user.Prefix)@$TenantDomain"
        $found = Get-Resources (Invoke-Db @("account", "users", "list", "--filter", "userName eq '$upn'"))
        if ($found.Count -gt 0) {
            Write-Host "  [skip]   User $upn exists"
            $userId = $found[0].id
        }
        else {
            Write-Host "  [create] User $upn" -ForegroundColor Green
            $file = New-TempJson @{ userName = $upn; displayName = $user.Display }
            try { $userId = (Invoke-Db @("account", "users", "create", "--json", "@$file")).id }
            finally { Remove-Item $file -ErrorAction SilentlyContinue }
        }
        Add-GroupMember -GroupId $groupIds[$user.Group] -GroupName $user.Group -PrincipalId $userId -Label $upn
    }

    Write-Host "`n=== 3. Account service principals ===" -ForegroundColor Cyan
    $cicdPrincipalId = $null
    foreach ($spn in $SERVICE_PRINCIPALS) {
        $appId = az ad app list --display-name $spn.Name `
            --query "[?displayName=='$($spn.Name)'].appId | [0]" -o tsv
        if ([string]::IsNullOrWhiteSpace($appId)) {
            Write-Host "  [warn]   $($spn.Name) not found in Entra ID - run sh/kv_spn_create.sh" -ForegroundColor Yellow
            continue
        }

        $found = Get-Resources (Invoke-Db @("account", "service-principals", "list", "--filter", "applicationId eq '$appId'"))
        if ($found.Count -gt 0) {
            Write-Host "  [skip]   Service principal $($spn.Name) exists"
            $spId = $found[0].id
        }
        else {
            Write-Host "  [create] Service principal $($spn.Name)" -ForegroundColor Green
            $file = New-TempJson @{ applicationId = $appId; displayName = $spn.Name }
            try { $spId = (Invoke-Db @("account", "service-principals", "create", "--json", "@$file")).id }
            finally { Remove-Item $file -ErrorAction SilentlyContinue }
        }

        Add-GroupMember -GroupId $groupIds[$spn.Group] -GroupName $spn.Group -PrincipalId $spId -Label $spn.Name
        if ($spn.Name -eq "spn-sovereignshield-cicd") { $cicdPrincipalId = $spId }
    }

    Write-Host "`n=== 4. Workspace assignment ===" -ForegroundColor Cyan
    $workspaceId = az databricks workspace show -g $ResourceGroup -n $WorkspaceName --query workspaceId -o tsv
    if ([string]::IsNullOrWhiteSpace($workspaceId)) {
        throw "Workspace $WorkspaceName not found in $ResourceGroup. Run sh/databricks_create.sh first."
    }

    $assigned = @{}
    $current = Invoke-Db @("account", "workspace-assignment", "list", $workspaceId)
    foreach ($item in (Get-Resources $current)) {
        if ($item.PSObject.Properties.Name -contains "principal" -and $item.principal) {
            $assigned[[string]$item.principal.principal_id] = $true
        }
    }

    # Groups get USER; the pipeline principal gets ADMIN so it can apply the
    # Triple-Lock DDL and own the resulting catalogue objects.
    $targets = @()
    foreach ($name in $GROUPS) { $targets += @{ Id = $groupIds[$name]; Label = $name; Permission = "USER" } }
    if ($cicdPrincipalId) {
        $targets += @{ Id = $cicdPrincipalId; Label = "spn-sovereignshield-cicd"; Permission = "ADMIN" }
    }

    foreach ($target in $targets) {
        if ($assigned.ContainsKey([string]$target.Id)) {
            Write-Host "  [skip]   $($target.Label) already assigned to the workspace"
            continue
        }
        Write-Host "  [create] Assigning $($target.Label) ($($target.Permission))" -ForegroundColor Green
        $file = New-TempJson @{ permissions = @($target.Permission) }
        try {
            Invoke-Db @("account", "workspace-assignment", "update", $workspaceId, [string]$target.Id, "--json", "@$file") | Out-Null
        }
        finally { Remove-Item $file -ErrorAction SilentlyContinue }
    }

    Write-Host "`n========================================================" -ForegroundColor Green
    Write-Host "Databricks account layer is in sync." -ForegroundColor Green
    Write-Host "Workspace ID : $workspaceId"
    Write-Host "========================================================" -ForegroundColor Green

    # ---------------------------------------------------------------------
    # 5. App service principal
    #
    # Databricks Apps mints its OWN managed service principal and injects its
    # credentials as DATABRICKS_CLIENT_ID/SECRET. That, not the Entra
    # spn-sovereignshield-public, is the identity anonymous portal requests
    # actually run as - so that is what has to hold the public tier.
    # ---------------------------------------------------------------------
    if ($appClientId) {
        Write-Host "`n=== 5. App service principal ===" -ForegroundColor Cyan
        $found = Get-Resources (Invoke-Db @("account", "service-principals", "list", "--filter", "applicationId eq '$appClientId'"))
        if ($found.Count -eq 0) {
            Write-Host "  [warn]   No account service principal for $appClientId yet; retry shortly." -ForegroundColor Yellow
        }
        else {
            Add-GroupMember -GroupId $groupIds["sg-sovereignshield-public"] `
                -GroupName "sg-sovereignshield-public" `
                -PrincipalId $found[0].id `
                -Label "$AppName (managed SP)"
            Write-Host "  Restart the app so it picks up the new membership." -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "`nNot yet done: after deploying the app, re-run with -AppName sovereignshield-portal"
        Write-Host "to grant its managed service principal the public tier."
    }
}
finally {
    $env:DATABRICKS_HOST = $saved.Host
    $env:DATABRICKS_ACCOUNT_ID = $saved.AccountId
    $env:ARM_CLIENT_ID = $saved.ClientId
    $env:ARM_CLIENT_SECRET = $saved.Secret
    $env:ARM_TENANT_ID = $saved.Tenant
}
