#!/bin/bash
# =====================================================================
# Provisions the Azure Databricks workspace and publishes its URL to Key Vault.
#
# IDEMPOTENT. An existing workspace is reused. The URL is written to the vault
# on every run because a rebuilt workspace gets a NEW url, and pre_auth.ps1
# reads it from there - a stale value authenticates against a workspace that no
# longer exists and fails with an opaque 401.
# =====================================================================

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-sovereignshield}"
LOCATION="${LOCATION:-canadacentral}"
WORKSPACE_NAME="${WORKSPACE_NAME:-dbw-sovereignshield}"
SKU="premium"   # Unity Catalog, row filters and column masks are premium-only.

echo "=== 1. Azure Databricks Workspace ($WORKSPACE_NAME) ==="
if az databricks workspace show --resource-group "$RESOURCE_GROUP" --name "$WORKSPACE_NAME" >/dev/null 2>&1; then
  echo "[skip]   Workspace already exists."
else
  echo "[create] Workspace $WORKSPACE_NAME"
  az databricks workspace create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WORKSPACE_NAME" \
    --location "$LOCATION" \
    --sku "$SKU" \
    --output none
fi

echo "=== 2. Retrieving Workspace Information ==="
WORKSPACE_URL=$(az databricks workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WORKSPACE_NAME" \
  --query "workspaceUrl" -o tsv)
WORKSPACE_ID=$(az databricks workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WORKSPACE_NAME" \
  --query "workspaceId" -o tsv)

echo "=== 3. Publishing the workspace URL to Key Vault ==="
KEYVAULT_NAME="${KEYVAULT_NAME:-$(az keyvault list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[?starts_with(name, 'kv-sovereignshield')].name | [0]" -o tsv 2>/dev/null || true)}"

if [ -z "$KEYVAULT_NAME" ]; then
  echo "[warn]   No Key Vault found - run sh/kv_spn_create.sh first, then re-run this script."
else
  CURRENT=$(az keyvault secret show --vault-name "$KEYVAULT_NAME" \
    --name "databricks-workspace-url" --query value -o tsv 2>/dev/null || true)
  if [ "$CURRENT" = "https://$WORKSPACE_URL" ]; then
    echo "[skip]   databricks-workspace-url already current."
  else
    echo "[create] Storing databricks-workspace-url in $KEYVAULT_NAME"
    az keyvault secret set --vault-name "$KEYVAULT_NAME" \
      --name "databricks-workspace-url" --value "https://$WORKSPACE_URL" --output none
  fi
fi

echo ""
echo "========================================================"
echo "Workspace Name : $WORKSPACE_NAME"
echo "Resource Group : $RESOURCE_GROUP"
echo "Workspace URL  : https://$WORKSPACE_URL"
echo "Workspace ID   : $WORKSPACE_ID"
echo "Key Vault      : ${KEYVAULT_NAME:-<none>}"
echo "========================================================"
