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
    # A GUID, not the workspace's numeric org id. Passing the org id reaches the CLI
    # as "The accountId could not be retrieved", which reads like an auth failure.
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')]
    [string]$AccountId,

    [string]$ResourceGroup = "rg-sovereignshield",
    [string]$WorkspaceName = "dbw-sovshield",
    [string]$TenantDomain = "13668754CANADAINC.onmicrosoft.com",
    [string]$AppName = "",
    [switch]$AppOnly
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
    $items = @()

    if ($null -ne $response) {
        # The CLI returns a bare array on some versions and an envelope on others,
        # keyed differently per endpoint.
        $envelopeKey = $null
        foreach ($key in @("Resources", "permission_assignments")) {
            if ($response.PSObject.Properties.Name -contains $key) { $envelopeKey = $key; break }
        }

        if ($envelopeKey) {
            if ($null -ne $response.$envelopeKey) { $items = @($response.$envelopeKey) }
        }
        elseif ($response -is [System.Management.Automation.PSCustomObject]) {
            # An object with no properties, or one carrying only a result count,
            # is an empty response rather than a single result. Wrapping it would
            # report one match and then read an id that was never there.
            $names = @($response.PSObject.Properties.Name)
            if ($names.Count -gt 0 -and -not ($names -contains "totalResults")) {
                $items = @($response)
            }
        }
        else {
            $items = @($response)
        }
    }

    # Returned bare, not as `, $items`. Every caller wraps the result in @(),
    # which normalises correctly. The comma idiom emits the array as a single
    # object, which turns "no matches" into one match holding an empty array.
    return $items
}

# The CLI has shipped several response shapes across versions. When one slips
# past Get-Resources, fail with the payload rather than a bare StrictMode
# "property 'id' cannot be found", which names neither the object nor the call.
function Get-ResourceId($resource, [string]$Label) {
    # Unwrap any array layer first. Piping to ConvertTo-Json would hide one,
    # because the pipeline unrolls before serialising - which is exactly how the
    # last round of this bug disguised itself as a missing field.
    $item = $resource
    while ($item -is [System.Array]) {
        if ($item.Count -lt 1) { break }
        $item = $item[0]
    }

    if ($null -ne $item -and $item.PSObject.Properties.Name -contains "id") {
        return [string]$item.id
    }

    $shape = try { ConvertTo-Json -InputObject $resource -Depth 3 -Compress } catch { "<unserialisable>" }
    throw "Databricks returned a result for '$Label' with no id field. Type: $($resource.GetType().Name). Response: $shape"
}

function New-TempJson($object) {
    $path = [System.IO.Path]::GetTempFileName()
    $json = $object | ConvertTo-Json -Depth 10 -Compress

    # Windows PowerShell writes a BOM for -Encoding utf8, and the CLI forwards
    # the file verbatim, so the leading EF BB BF breaks JSON parsing server-side.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $json, $utf8NoBom)
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

function Add-ServicePrincipalEntitlement {
    param(
        [string]$PrincipalId,
        [string]$Label,
        [string]$Entitlement,
        [switch]$WorkspaceScope
    )

    [string[]]$commandPrefix = if ($WorkspaceScope) {
        "service-principals"
    } else {
        "account"
        "service-principals"
    }
    $principal = Invoke-Db -Arguments ($commandPrefix + @("get", $PrincipalId))
    $existing = @()
    if ($principal.PSObject.Properties.Name -contains "entitlements" -and $principal.entitlements) {
        $existing = @($principal.entitlements | ForEach-Object { $_.value })
    }
    if ($existing -contains $Entitlement) {
        Write-Host "  [skip]   $Label already has $Entitlement"
        return
    }

    Write-Host "  [create] Granting $Entitlement to $Label" -ForegroundColor Green
    $payload = @{
        schemas    = @("urn:ietf:params:scim:api:messages:2.0:PatchOp")
        Operations = @(@{
            op    = "add"
            path  = "entitlements"
            value = @(@{ value = $Entitlement })
        })
    }
    $file = New-TempJson $payload
    try { Invoke-Db -Arguments ($commandPrefix + @("patch", $PrincipalId, "--json", "@$file")) | Out-Null }
    finally { Remove-Item $file -ErrorAction SilentlyContinue }
}

try {
    if ($AppOnly) {
        if (-not $appClientId) { throw "-AppOnly requires -AppName." }

        Write-Host "=== App service principal ===" -ForegroundColor Cyan
        $publicGroups = @(Get-Resources (Invoke-Db @(
            "account", "groups", "list", "--filter",
            "displayName eq 'sg-sovereignshield-public'"
        )))
        if ($publicGroups.Count -eq 0) {
            throw "sg-sovereignshield-public does not exist. Run the full account setup first."
        }

        $appPrincipals = @(Get-Resources (Invoke-Db @(
            "account", "service-principals", "list", "--filter",
            "applicationId eq '$appClientId'"
        )))
        if ($appPrincipals.Count -eq 0) {
            throw "No account service principal exists yet for app '$AppName'."
        }

        Add-GroupMember `
            -GroupId (Get-ResourceId $publicGroups[0] "group sg-sovereignshield-public") `
            -GroupName "sg-sovereignshield-public" `
            -PrincipalId (Get-ResourceId $appPrincipals[0] "$AppName managed SP") `
            -Label "$AppName (managed SP)"
        return
    }

    Write-Host "=== 1. Account groups ===" -ForegroundColor Cyan
    $groupIds = @{}
    foreach ($name in $GROUPS) {
        $found = @(Get-Resources (Invoke-Db @("account", "groups", "list", "--filter", "displayName eq '$name'")))
        if ($found.Count -gt 0) {
            Write-Host "  [skip]   Group $name exists"
            $groupIds[$name] = Get-ResourceId $found[0] "group $name"
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
        $found = @(Get-Resources (Invoke-Db @("account", "users", "list", "--filter", "userName eq '$upn'")))
        if ($found.Count -gt 0) {
            Write-Host "  [skip]   User $upn exists"
            $userId = Get-ResourceId $found[0] "user $upn"
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
    $publicPrincipalId = $null
    foreach ($spn in $SERVICE_PRINCIPALS) {
        $appId = az ad app list --display-name $spn.Name `
            --query "[?displayName=='$($spn.Name)'].appId | [0]" -o tsv
        if ([string]::IsNullOrWhiteSpace($appId)) {
            Write-Host "  [warn]   $($spn.Name) not found in Entra ID - run sh/kv_spn_create.sh" -ForegroundColor Yellow
            continue
        }

        $found = @(Get-Resources (Invoke-Db @("account", "service-principals", "list", "--filter", "applicationId eq '$appId'")))
        if ($found.Count -gt 0) {
            Write-Host "  [skip]   Service principal $($spn.Name) exists"
            $spId = Get-ResourceId $found[0] "service principal $($spn.Name)"
        }
        else {
            Write-Host "  [create] Service principal $($spn.Name)" -ForegroundColor Green
            $file = New-TempJson @{ applicationId = $appId; displayName = $spn.Name }
            try { $spId = (Invoke-Db @("account", "service-principals", "create", "--json", "@$file")).id }
            finally { Remove-Item $file -ErrorAction SilentlyContinue }
        }

        Add-GroupMember -GroupId $groupIds[$spn.Group] -GroupName $spn.Group -PrincipalId $spId -Label $spn.Name
        if ($spn.Name -eq "spn-sovereignshield-cicd") { $cicdPrincipalId = $spId }
        if ($spn.Name -eq "spn-sovereignshield-public") {
            $publicPrincipalId = $spId
        }
    }

    Write-Host "`n=== 4. Workspace assignment ===" -ForegroundColor Cyan
    $workspaceId = az databricks workspace show -g $ResourceGroup -n $WorkspaceName --query workspaceId -o tsv
    if ([string]::IsNullOrWhiteSpace($workspaceId)) {
        throw "Workspace $WorkspaceName not found in $ResourceGroup. Run sh/databricks_create.sh first."
    }

    $assigned = @{}
    $current = Invoke-Db @("account", "workspace-assignment", "list", $workspaceId)
    foreach ($item in @(Get-Resources $current)) {
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
    if ($publicPrincipalId) {
        $targets += @{ Id = $publicPrincipalId; Label = "spn-sovereignshield-public"; Permission = "USER" }
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

    if ($publicPrincipalId) {
        $workspaceHost = az databricks workspace show -g $ResourceGroup -n $WorkspaceName --query workspaceUrl -o tsv
        $accountHost = $env:DATABRICKS_HOST
        $accountIdValue = $env:DATABRICKS_ACCOUNT_ID
        try {
            $env:DATABRICKS_HOST = "https://$workspaceHost"
            $env:DATABRICKS_ACCOUNT_ID = $null
            Add-ServicePrincipalEntitlement -PrincipalId $publicPrincipalId `
                -Label "spn-sovereignshield-public" `
                -Entitlement "databricks-sql-access" -WorkspaceScope
        }
        finally {
            $env:DATABRICKS_HOST = $accountHost
            $env:DATABRICKS_ACCOUNT_ID = $accountIdValue
        }
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
        $found = @(Get-Resources (Invoke-Db @("account", "service-principals", "list", "--filter", "applicationId eq '$appClientId'")))
        if ($found.Count -eq 0) {
            Write-Host "  [warn]   No account service principal for $appClientId yet; retry shortly." -ForegroundColor Yellow
        }
        else {
            Add-GroupMember -GroupId $groupIds["sg-sovereignshield-public"] `
                -GroupName "sg-sovereignshield-public" `
                -PrincipalId (Get-ResourceId $found[0] "$AppName managed SP") `
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
