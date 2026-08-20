#!/bin/bash
# =====================================================================
# Deploys the SovereignShield portal to Azure Container Apps with
# genuinely anonymous public access.
#
# A Databricks App always sits behind workspace SSO, so its "public" tier is an
# authenticated visitor holding no sovereign entitlement. That proves the
# persona matrix but not the anonymous case. Container Apps closes the gap: the
# same image, reachable from the open internet with no login, running as
# spn-sovereignshield-public - whose entire entitlement is the Unity Catalog row
# filter attached to sg-sovereignshield-public.
#
# Nothing about the security model changes. The row filter is still the only
# thing deciding what a caller sees; this script only changes who can knock.
#
# Usage:
#   ./sh/container_apps_deploy.sh <key-vault-name> <databricks-host> <warehouse-id> [--with-entra-signin]
#
# Requires the Key Vault produced by sh/kv_spn_create.sh, which holds
# public-spn-client-id and public-spn-client-secret.
# =====================================================================

set -euo pipefail

KEYVAULT_NAME="${1:?Key Vault name is required}"
DATABRICKS_HOST="${2:?Databricks workspace hostname is required (no https://)}"
WAREHOUSE_ID="${3:?SQL warehouse id is required}"
ENABLE_SIGNIN="${4:-}"

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-sovereignshield}"
LOCATION="${LOCATION:-canadacentral}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-cae-sovereignshield}"
APP_NAME="${APP_NAME:-ca-sovereignshield-portal}"
REGISTRY_NAME="${REGISTRY_NAME:-acrsovereignshield$RANDOM}"

# Resource id of the first-party AzureDatabricks application. An Entra token is
# only accepted by the workspace if it was issued for this audience.
AZURE_DATABRICKS_RESOURCE_ID="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="sovereignshield-portal:$(date -u +%Y%m%d%H%M%S)"

echo "==> 1/8 Registering providers and the containerapp extension"
az extension add --name containerapp --upgrade --only-show-errors >/dev/null
az provider register --namespace Microsoft.App --wait >/dev/null
az provider register --namespace Microsoft.OperationalInsights --wait >/dev/null

echo "==> 2/8 Creating the container registry ($REGISTRY_NAME)"
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$REGISTRY_NAME" \
  --sku Basic \
  --location "$LOCATION" \
  --output none

echo "==> 3/8 Building the image in ACR (no local Docker required)"
az acr build \
  --registry "$REGISTRY_NAME" \
  --image "$IMAGE_TAG" \
  --file "$REPO_ROOT/Dockerfile" \
  "$REPO_ROOT" \
  --output none

echo "==> 4/8 Creating the Container Apps environment"
az containerapp env create \
  --name "$ENVIRONMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

echo "==> 5/8 Deploying the app with external ingress"
# Ingress is external and unauthenticated by design - this deployment exists to
# demonstrate the anonymous tier. The app holds no state, so scaling out is safe.
az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT_NAME" \
  --image "$REGISTRY_NAME.azurecr.io/$IMAGE_TAG" \
  --registry-server "$REGISTRY_NAME.azurecr.io" \
  --registry-identity system \
  --system-assigned \
  --ingress external \
  --target-port 8000 \
  --transport auto \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --output none

PRINCIPAL_ID=$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query identity.principalId -o tsv)
VAULT_ID=$(az keyvault show --name "$KEYVAULT_NAME" --query id -o tsv)

echo "==> 6/8 Granting the app identity read access to $KEYVAULT_NAME"
# Works whether the vault uses RBAC or access policies; one of the two is a no-op.
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID" \
  --output none 2>/dev/null || true
az keyvault set-policy --name "$KEYVAULT_NAME" --object-id "$PRINCIPAL_ID" \
  --secret-permissions get list --output none 2>/dev/null || true

echo "==> 7/8 Wiring Key Vault references and environment"
# Credentials are Key Vault references resolved by the platform at start-up.
# No secret value is ever passed on a command line, written to a file, or echoed.
VAULT_URI="https://$KEYVAULT_NAME.vault.azure.net/secrets"
az containerapp secret set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets \
    "public-spn-client-id=keyvaultref:$VAULT_URI/public-spn-client-id,identityref:system" \
    "public-spn-client-secret=keyvaultref:$VAULT_URI/public-spn-client-secret,identityref:system" \
  --output none

az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars \
    "DATABRICKS_HOST=$DATABRICKS_HOST" \
    "DATABRICKS_SERVER_HOSTNAME=$DATABRICKS_HOST" \
    "DATABRICKS_WAREHOUSE_ID=$WAREHOUSE_ID" \
    "DATABRICKS_CLIENT_ID=secretref:public-spn-client-id" \
    "DATABRICKS_CLIENT_SECRET=secretref:public-spn-client-secret" \
    "SOVEREIGNSHIELD_CATALOG=dbw_sovereignshield" \
    "SOVEREIGNSHIELD_SCHEMA=sovereign_shield" \
  --output none

FQDN=$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

if [ "$ENABLE_SIGNIN" = "--with-entra-signin" ]; then
  echo "==> 8/8 Enabling Entra ID sign-in alongside anonymous access"

  AUTH_APP_ID=$(az ad app create \
    --display-name "app-sovereignshield-portal" \
    --web-redirect-uris "https://$FQDN/.auth/login/aad/callback" \
    --query appId -o tsv)

  # The forwarded token must be issued for the AzureDatabricks resource,
  # otherwise the workspace rejects it and every signed-in caller silently falls
  # back to the public tier.
  az ad app permission add \
    --id "$AUTH_APP_ID" \
    --api "$AZURE_DATABRICKS_RESOURCE_ID" \
    --api-permissions "739272be-e143-11e8-9f32-f2801f1b9fd1=Scope" \
    --output none

  AUTH_SECRET=$(az ad app credential reset --id "$AUTH_APP_ID" --append --query password -o tsv)
  az containerapp secret set \
    --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --secrets "portal-auth-secret=$AUTH_SECRET" --output none
  unset AUTH_SECRET

  az containerapp auth microsoft update \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --client-id "$AUTH_APP_ID" \
    --client-secret-name "portal-auth-secret" \
    --tenant-id "$(az account show --query tenantId -o tsv)" \
    --yes --output none

  # AllowAnonymous is the whole point: an unauthenticated visitor is served the
  # public tier, and /.auth/login/aad elevates them on demand.
  az containerapp auth update \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --unauthenticated-client-action AllowAnonymous \
    --enable-token-store true \
    --output none

  echo
  echo "Manual step: add the Databricks scope to the login request."
  echo "  Container App > Authentication > Microsoft > Edit > Login parameters:"
  echo "    scope=openid profile $AZURE_DATABRICKS_RESOURCE_ID/user_impersonation"
  echo "  Without it the forwarded token has the wrong audience and every"
  echo "  signed-in visitor silently stays on the public tier."
else
  echo "==> 8/8 Skipping Entra sign-in (anonymous tier only)"
fi

echo
echo "Portal:  https://$FQDN"
echo "API:     https://$FQDN/api/v1/search"
echo "Health:  https://$FQDN/api/v1/health"
echo
echo "Verify the anonymous tier is genuinely fail-closed:"
echo "  curl -s \"https://$FQDN/api/v1/search?limit=5\" | jq '.observations[] | {BATCH_STATUS, OBS_CONF}'"
echo "Every returned observation must carry BATCH_STATUS=PUBLISHED and OBS_CONF=F."
