#!/bin/bash
# =====================================================================
# ROTATION, not provisioning. Deliberately destructive: it deletes the existing
# app registration and mints fresh credentials, killing any copy a departing
# builder retained. Use sh/kv_spn_create.sh for the idempotent create path.
# =====================================================================
set -e

RESOURCE_GROUP="rg-sovereignshield"
LOCATION="canadacentral"
SPN_NAME="spn-sovereignshield-cicd"

# Discovered, not hardcoded - the vault name carries a $RANDOM suffix.
KEYVAULT_NAME="${KEYVAULT_NAME:-$(az keyvault list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[?starts_with(name, 'kv-sovereignshield')].name | [0]" -o tsv)}"

if [ -z "$KEYVAULT_NAME" ]; then
    echo "ERROR: No Key Vault matching 'kv-sovereignshield*' in $RESOURCE_GROUP."
    exit 1
fi

echo "=== 1. Cleaning up existing Service Principal if present ==="
OLD_APP_ID=$(az ad app list --display-name "$SPN_NAME" --query "[0].appId" -o tsv)
if [ -n "$OLD_APP_ID" ]; then
    echo "Deleting existing SPN App ID: $OLD_APP_ID..."
    az ad app delete --id "$OLD_APP_ID"
fi

echo "=== 2. Creating fresh Service Principal ($SPN_NAME) ==="
SPN_JSON=$(az ad sp create-for-rbac --name "$SPN_NAME" --output json)

SPN_APP_ID=$(echo "$SPN_JSON" | jq -r '.appId')
SPN_SECRET=$(echo "$SPN_JSON" | jq -r '.password')
SPN_TENANT_ID=$(echo "$SPN_JSON" | jq -r '.tenant')

if [ -z "$SPN_APP_ID" ] || [ "$SPN_APP_ID" == "null" ]; then
    echo "ERROR: Failed to extract Service Principal credentials."
    exit 1
fi

echo "Service Principal Created Successfully!"
echo "App ID: $SPN_APP_ID"

echo "=== 3. Storing Credentials in Key Vault ($KEYVAULT_NAME) ==="
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-client-id" --value "$SPN_APP_ID" --output none
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-client-secret" --value "$SPN_SECRET" --output none
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-tenant-id" --value "$SPN_TENANT_ID" --output none

echo "=== Success! Zero-Trust Key Vault & SPN Configured ==="
echo "Key Vault Name: $KEYVAULT_NAME"
echo "Resource Group: $RESOURCE_GROUP ($LOCATION)"