#!/bin/bash

RESOURCE_GROUP="rg-sovereignshield"
LOCATION="canadacentral"
KEYVAULT_NAME="kv-sovereignshield-$RANDOM"

echo "1. Creating Resource Group if it doesn't exist..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

echo "2. Creating Service Principal (spn-sovereignshield-cicd)..."
SPN_JSON=$(az ad sp create-for-rbac --name "spn-sovereignshield-cicd" --skip-assignment --output json)

SPN_APP_ID=$(echo$SPN_JSON | jq -r '.appId')
SPN_SECRET=$(echo$SPN_JSON | jq -r '.password')
SPN_TENANT_ID=$(echo$SPN_JSON | jq -r '.tenant')

echo "Service Principal Created: $SPN_APP_ID"

echo "3. Creating Azure Key Vault ($KEYVAULT_NAME)..."
az keyvault create \
  --name "$KEYVAULT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --enable-rbac-authorization false

echo "4. Storing SPN Credentials in Key Vault..."
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-client-id" --value "$SPN_APP_ID"
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-client-secret" --value "$SPN_SECRET"
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-tenant-id" --value "$SPN_TENANT_ID"

# =====================================================================
# 5. PUBLIC PORTAL PROXY IDENTITY (spn-sovereignshield-public)
#
# The identity every unauthenticated portal request runs as. It is created
# WITHOUT any Azure RBAC role assignment - create-for-rbac would grant it
# Contributor over the subscription, and this principal has no business
# touching the control plane. Its entire entitlement is the Unity Catalog row
# filter attached to sg-sovereignshield-public: published, free-to-publish rows.
# =====================================================================
echo "5. Creating Public Portal Proxy SPN (spn-sovereignshield-public)..."
PUBLIC_APP_ID=$(az ad app create --display-name "spn-sovereignshield-public" --query appId -o tsv)
az ad sp create --id "$PUBLIC_APP_ID" --output none
PUBLIC_SECRET=$(az ad app credential reset --id "$PUBLIC_APP_ID" --append --query password -o tsv)
PUBLIC_OBJECT_ID=$(az ad sp show --id "$PUBLIC_APP_ID" --query id -o tsv)

echo "6. Adding the proxy SPN to sg-sovereignshield-public..."
az ad group member add --group "sg-sovereignshield-public" --member-id "$PUBLIC_OBJECT_ID"

echo "7. Storing Public Proxy Credentials in Key Vault..."
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "public-spn-client-id" --value "$PUBLIC_APP_ID"
az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "public-spn-client-secret" --value "$PUBLIC_SECRET"

echo "Zero-Trust Key Vault & SPN Provisioned Successfully."
echo "Key Vault Name: $KEYVAULT_NAME"
echo "Public Proxy App ID: $PUBLIC_APP_ID"
echo
echo "Next: add spn-sovereignshield-public as a Databricks account service principal"
echo "and confirm its sg-sovereignshield-public membership synchronised, otherwise the"
echo "row filter fails closed and the public portal shows nothing."