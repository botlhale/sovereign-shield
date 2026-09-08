$ErrorActionPreference = "Stop"

$ResourceGroup = if ($env:RESOURCE_GROUP) { $env:RESOURCE_GROUP } else { "rg-sovereignshield" }

# Discovered rather than hardcoded: both paths suffix the vault name randomly
# (kv_spn_create.sh with $RANDOM, Terraform with random_integer), so a
# re-provisioned environment gets a different name every time. A stale literal
# here fails at the first secret lookup and looks like a Key Vault permissions
# problem rather than a wrong name.
$KeyVaultName = if ($env:KEYVAULT_NAME) {
    $env:KEYVAULT_NAME
} else {
    az keyvault list --resource-group $ResourceGroup `
        --query "[?starts_with(name, 'kv-sovereignshield')].name | [0]" -o tsv
}

if ([string]::IsNullOrWhiteSpace($KeyVaultName)) {
    throw "No Key Vault matching 'kv-sovereignshield*' found in $ResourceGroup. Run sh/kv_spn_create.sh, or set `$env:KEYVAULT_NAME."
}

Write-Host "Retrieving deployment credentials from $KeyVaultName..." -ForegroundColor Cyan

function Get-VaultSecret {
    param([string]$Name, [switch]$Optional)

    # Redirecting a native command's stderr while the preference is Stop turns
    # the first stderr line into a terminating error, which would defeat
    # -Optional before it is ever evaluated.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $value = az keyvault secret show --vault-name $KeyVaultName --name $Name --query value -o tsv 2>$null
    } finally {
        $ErrorActionPreference = $previous
    }

    if ([string]::IsNullOrWhiteSpace($value)) {
        if ($Optional) { return $null }
        throw "Secret '$Name' is missing from $KeyVaultName."
    }

    # .Trim() is load-bearing: az -o tsv appends a newline, and an unstripped
    # secret produces an opaque authentication rejection rather than a parse error.
    return $value.Trim()
}

$env:DATABRICKS_HOST = Get-VaultSecret "databricks-workspace-url"

# Which credential to load is decided by what the provisioning path stored, not
# by a flag. kv_spn_create.sh mints a CI/CD secret and writes it here; Terraform
# federates that same identity to GitHub OIDC and deliberately never creates a
# secret, so on that path there is nothing to load and the operator's own
# Azure CLI session is the credential.
$clientId = Get-VaultSecret "spn-client-id" -Optional

if ($clientId) {
    $env:ARM_CLIENT_ID        = $clientId
    $env:ARM_CLIENT_SECRET    = Get-VaultSecret "spn-client-secret"
    $env:ARM_TENANT_ID        = Get-VaultSecret "spn-tenant-id"
    $env:DATABRICKS_AUTH_TYPE = "azure-client-secret"
    $identity = "service principal $clientId"
} else {
    # Cleared, not just left unset: a value lingering from an earlier run in this
    # session would be picked up ahead of the CLI credential and rejected by a
    # workspace that has never heard of it.
    Remove-Item Env:ARM_CLIENT_ID, Env:ARM_CLIENT_SECRET -ErrorAction SilentlyContinue

    $env:ARM_TENANT_ID        = Get-VaultSecret "spn-tenant-id"
    $env:DATABRICKS_AUTH_TYPE = "azure-cli"

    $signedIn = az account show --query user.name -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($signedIn)) {
        throw "No CI/CD secret in $KeyVaultName and no Azure CLI session. Run 'az login'."
    }
    $identity = "Azure CLI user $signedIn"
}

Write-Host "Authentication environment variables set successfully!" -ForegroundColor Green
Write-Host "  Workspace: $env:DATABRICKS_HOST" -ForegroundColor DarkGray
Write-Host "  Identity:  $identity" -ForegroundColor DarkGray
