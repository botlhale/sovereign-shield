$ErrorActionPreference = "Stop"

$ResourceGroup = if ($env:RESOURCE_GROUP) { $env:RESOURCE_GROUP } else { "rg-sovereignshield" }

# Discovered rather than hardcoded: kv_spn_create.sh suffixes the vault name with
# $RANDOM, so a re-provisioned environment gets a different name every time. A
# stale literal here fails at the first secret lookup and looks like a Key Vault
# permissions problem rather than a wrong name.
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

function Get-VaultSecret([string]$Name) {
    # .Trim() is load-bearing: az -o tsv appends a newline, and an unstripped
    # secret produces an opaque authentication rejection rather than a parse error.
    $value = (az keyvault secret show --vault-name $KeyVaultName --name $Name --query value -o tsv)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Secret '$Name' is missing from $KeyVaultName."
    }
    return $value.Trim()
}

$env:DATABRICKS_HOST   = Get-VaultSecret "databricks-workspace-url"
$env:ARM_CLIENT_ID     = Get-VaultSecret "spn-client-id"
$env:ARM_CLIENT_SECRET = Get-VaultSecret "spn-client-secret"
$env:ARM_TENANT_ID     = Get-VaultSecret "spn-tenant-id"

Write-Host "Authentication environment variables set successfully!" -ForegroundColor Green
Write-Host "  Workspace: $env:DATABRICKS_HOST" -ForegroundColor DarkGray
