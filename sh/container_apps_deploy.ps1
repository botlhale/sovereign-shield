<#
.SYNOPSIS
    Deploys the SovereignShield portal to Azure Container Apps with genuinely
    anonymous public access.

.DESCRIPTION
    A Databricks App always sits behind workspace SSO, so its "public" tier is
    an authenticated visitor holding no sovereign entitlement. That proves the
    persona matrix but not the anonymous case. Container Apps closes the gap:
    the same image, reachable from the open internet with no login, running as
    spn-sovereignshield-public - whose entire entitlement is the Unity Catalog
    row filter attached to sg-sovereignshield-public.

    Nothing about the security model changes. The row filter is still the only
    thing deciding what a caller sees; this script only changes who can knock.

    Optionally enables Entra ID sign-in (-EnableEntraSignIn) so the elevated
    personas can be demonstrated from the same URL. Container Apps built-in
    authentication then forwards the caller's token as
    X-MS-TOKEN-AAD-ACCESS-TOKEN, which the gateway already understands.

.EXAMPLE
    ./sh/container_apps_deploy.ps1 -KeyVaultName kv-sovereignshield-28083 `
        -DatabricksHost adb-7405605868991128.8.azuredatabricks.net `
        -WarehouseId abcd1234efgh5678

.NOTES
    Requires: Azure CLI with the containerapp extension, and an existing
    Key Vault holding public-spn-client-id / public-spn-client-secret
    (created by sh/kv_spn_create.sh).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$KeyVaultName,
    [Parameter(Mandatory = $true)][string]$DatabricksHost,
    [Parameter(Mandatory = $true)][string]$WarehouseId,
    [string]$ResourceGroup = "rg-sovereignshield",
    [string]$Location = "canadacentral",
    [string]$EnvironmentName = "cae-sovereignshield",
    [string]$AppName = "ca-sovereignshield-portal",
    [string]$RegistryName = "",
    [switch]$EnableEntraSignIn
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Resource id of the first-party AzureDatabricks application. An Entra token is
# only accepted by the workspace if it was issued for this audience.
$AzureDatabricksResourceId = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"

$repoRoot = Split-Path -Parent $PSScriptRoot
$imageTag = "sovereignshield-portal:$(Get-Date -Format yyyyMMddHHmmss)"

Write-Host "==> 1/8 Registering providers and the containerapp extension" -ForegroundColor Cyan
az extension add --name containerapp --upgrade --only-show-errors | Out-Null
az provider register --namespace Microsoft.App --wait | Out-Null
az provider register --namespace Microsoft.OperationalInsights --wait | Out-Null

Write-Host "==> 2/8 Container registry" -ForegroundColor Cyan
# The registry name carries a random suffix, so an existing one is discovered
# rather than recomputed - a new name would orphan the previous registry.
if (-not $RegistryName) {
    $RegistryName = az acr list --resource-group $ResourceGroup `
        --query "[?starts_with(name, 'acrsovereignshield')].name | [0]" -o tsv
}
if ($RegistryName) {
    Write-Host "    [skip]   Registry $RegistryName exists"
}
else {
    $RegistryName = "acrsovereignshield$((Get-Random -Maximum 99999))"
    Write-Host "    [create] Registry $RegistryName" -ForegroundColor Green
    az acr create `
        --resource-group $ResourceGroup `
        --name $RegistryName `
        --sku Basic `
        --location $Location `
        --output none
}

Write-Host "==> 3/8 Building the image in ACR (no local Docker required)" -ForegroundColor Cyan
# Always rebuilt: the point of re-running is to ship new code.
az acr build `
    --registry $RegistryName `
    --image $imageTag `
    --file (Join-Path $repoRoot "Dockerfile") `
    $repoRoot `
    --output none

Write-Host "==> 4/8 Container Apps environment" -ForegroundColor Cyan
if (az containerapp env show --name $EnvironmentName --resource-group $ResourceGroup 2>$null) {
    Write-Host "    [skip]   Environment $EnvironmentName exists"
}
else {
    Write-Host "    [create] Environment $EnvironmentName" -ForegroundColor Green
    az containerapp env create `
        --name $EnvironmentName `
        --resource-group $ResourceGroup `
        --location $Location `
        --output none
}

Write-Host "==> 5/8 Deploying the app with external ingress" -ForegroundColor Cyan
# Ingress is external and unauthenticated by design - this deployment exists to
# demonstrate the anonymous tier. minReplicas 1 keeps the first visitor off a
# cold start; the app holds no state, so scaling out is safe.
if (az containerapp show --name $AppName --resource-group $ResourceGroup 2>$null) {
    Write-Host "    [update] App $AppName exists - rolling out the new image" -ForegroundColor Green
    az containerapp update `
        --name $AppName `
        --resource-group $ResourceGroup `
        --image "$RegistryName.azurecr.io/$imageTag" `
        --output none
}
else {
    Write-Host "    [create] App $AppName" -ForegroundColor Green
    az containerapp create `
        --name $AppName `
        --resource-group $ResourceGroup `
        --environment $EnvironmentName `
        --image "$RegistryName.azurecr.io/$imageTag" `
        --registry-server "$RegistryName.azurecr.io" `
        --registry-identity system `
        --system-assigned `
        --ingress external `
        --target-port 8000 `
        --transport auto `
        --min-replicas 1 `
        --max-replicas 3 `
        --cpu 0.5 `
        --memory 1.0Gi `
        --output none
}

$principalId = az containerapp show --name $AppName --resource-group $ResourceGroup `
    --query identity.principalId -o tsv
$vaultId = az keyvault show --name $KeyVaultName --query id -o tsv

Write-Host "==> 6/8 Granting the app identity read access to $KeyVaultName" -ForegroundColor Cyan
# Works whether the vault uses RBAC or access policies; one of the two is a no-op.
az role assignment create `
    --assignee-object-id $principalId `
    --assignee-principal-type ServicePrincipal `
    --role "Key Vault Secrets User" `
    --scope $vaultId `
    --output none 2>$null
az keyvault set-policy --name $KeyVaultName --object-id $principalId `
    --secret-permissions get list --output none 2>$null

Write-Host "==> 7/8 Wiring Key Vault references and environment" -ForegroundColor Cyan
# Credentials are Key Vault references resolved by the platform at start-up.
# No secret value is ever passed on a command line, written to a file, or echoed.
$vaultUri = "https://$KeyVaultName.vault.azure.net/secrets"
az containerapp secret set `
    --name $AppName `
    --resource-group $ResourceGroup `
    --secrets `
        "public-spn-client-id=keyvaultref:$vaultUri/public-spn-client-id,identityref:system" `
        "public-spn-client-secret=keyvaultref:$vaultUri/public-spn-client-secret,identityref:system" `
    --output none

az containerapp update `
    --name $AppName `
    --resource-group $ResourceGroup `
    --set-env-vars `
        "DATABRICKS_HOST=$DatabricksHost" `
        "DATABRICKS_SERVER_HOSTNAME=$DatabricksHost" `
        "DATABRICKS_WAREHOUSE_ID=$WarehouseId" `
        "DATABRICKS_CLIENT_ID=secretref:public-spn-client-id" `
        "DATABRICKS_CLIENT_SECRET=secretref:public-spn-client-secret" `
        "SOVEREIGNSHIELD_CATALOG=dbw_sovereignshield" `
        "SOVEREIGNSHIELD_SCHEMA=sovereign_shield" `
    --output none

$fqdn = az containerapp show --name $AppName --resource-group $ResourceGroup `
    --query properties.configuration.ingress.fqdn -o tsv

if ($EnableEntraSignIn) {
    Write-Host "==> 8/8 Enabling Entra ID sign-in alongside anonymous access" -ForegroundColor Cyan

    $replyUrl = "https://$fqdn/.auth/login/aad/callback"
    $authAppId = az ad app list --display-name "app-sovereignshield-portal" `
        --query "[?displayName=='app-sovereignshield-portal'].appId | [0]" -o tsv

    if ($authAppId) {
        Write-Host "    [skip]   Entra app registration exists ($authAppId)"
        # The FQDN changes if the app is recreated, so the reply URL is refreshed.
        az ad app update --id $authAppId --web-redirect-uris $replyUrl --output none
    }
    else {
        Write-Host "    [create] Entra app registration" -ForegroundColor Green
        $authAppId = az ad app create `
            --display-name "app-sovereignshield-portal" `
            --web-redirect-uris $replyUrl `
            --query appId -o tsv
    }

    # The forwarded token must be issued for the AzureDatabricks resource,
    # otherwise the workspace rejects it and every signed-in caller falls back
    # to the public tier without any visible error.
    az ad app permission add `
        --id $authAppId `
        --api $AzureDatabricksResourceId `
        --api-permissions "739272be-e143-11e8-9f32-f2801f1b9fd1=Scope" `
        --output none 2>$null

    # Only minted when the container app has no stored secret: resetting one
    # that already works would break the running sign-in flow.
    $hasAuthSecret = az containerapp secret list --name $AppName --resource-group $ResourceGroup `
        --query "[?name=='portal-auth-secret'] | [0].name" -o tsv
    if ($hasAuthSecret) {
        Write-Host "    [skip]   portal-auth-secret already set"
    }
    else {
        Write-Host "    [create] portal-auth-secret" -ForegroundColor Green
        $authSecret = az ad app credential reset --id $authAppId --append --query password -o tsv
        az containerapp secret set `
            --name $AppName --resource-group $ResourceGroup `
            --secrets "portal-auth-secret=$authSecret" --output none
        Remove-Variable authSecret
    }

    az containerapp auth microsoft update `
        --name $AppName `
        --resource-group $ResourceGroup `
        --client-id $authAppId `
        --client-secret-name "portal-auth-secret" `
        --tenant-id (az account show --query tenantId -o tsv) `
        --yes --output none

    # AllowAnonymous is the whole point: an unauthenticated visitor is served
    # the public tier, and /.auth/login/aad elevates them on demand.
    az containerapp auth update `
        --name $AppName `
        --resource-group $ResourceGroup `
        --unauthenticated-client-action AllowAnonymous `
        --enable-token-store true `
        --output none

    Write-Host ""
    Write-Host "Manual step: add the Databricks scope to the login request." -ForegroundColor Yellow
    Write-Host "  Entra portal > App registrations > app-sovereignshield-portal > Authentication"
    Write-Host "  Container App > Authentication > Microsoft > Edit > Login parameters:"
    Write-Host "    scope=openid profile $AzureDatabricksResourceId/user_impersonation"
    Write-Host "  Without it the forwarded token has the wrong audience and every"
    Write-Host "  signed-in visitor silently stays on the public tier."
}
else {
    Write-Host "==> 8/8 Skipping Entra sign-in (anonymous tier only)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Portal:  https://$fqdn" -ForegroundColor Green
Write-Host "API:     https://$fqdn/api/v1/search" -ForegroundColor Green
Write-Host "Health:  https://$fqdn/api/v1/health" -ForegroundColor Green
Write-Host ""
Write-Host "Verify the anonymous tier is genuinely fail-closed:" -ForegroundColor Yellow
Write-Host "  curl 'https://$fqdn/api/v1/search?limit=5' | ConvertFrom-Json"
Write-Host "Every returned observation must carry BATCH_STATUS=PUBLISHED and OBS_CONF=F."
