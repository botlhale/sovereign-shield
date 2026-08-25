#!/bin/bash
# =====================================================================
# Provisions the SovereignShield trust root: Key Vault, the CI/CD service
# principal, and the public portal proxy service principal.
#
# IDEMPOTENT. Every resource is checked before it is created, so re-running
# after a partial teardown adds only what is missing.
#
# Credentials are minted only when the matching Key Vault secret is absent.
# Resetting a credential that is already stored would invalidate the copy the
# pipeline is using - a silent break that surfaces as a 401 on the next deploy.
# Use sh/kv_spn_remediation.sh when you actually intend to rotate.
#
# Override the vault with:  KEYVAULT_NAME=kv-... bash sh/kv_spn_create.sh
# =====================================================================

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-sovereignshield}"
LOCATION="${LOCATION:-canadacentral}"
CICD_SPN_NAME="spn-sovereignshield-cicd"
PUBLIC_SPN_NAME="spn-sovereignshield-public"
PUBLIC_GROUP_NAME="sg-sovereignshield-public"

secret_exists() {
  az keyvault secret show --vault-name "$1" --name "$2" --query id -o tsv >/dev/null 2>&1
}

app_id_for() {
  az ad app list --display-name "$1" --query "[?displayName=='$1'].appId | [0]" -o tsv 2>/dev/null || true
}

# ---------------------------------------------------------------------
# 1. Resource group
# ---------------------------------------------------------------------
if az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "[skip]   Resource group $RESOURCE_GROUP already exists."
else
  echo "[create] Resource group $RESOURCE_GROUP"
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
fi

# ---------------------------------------------------------------------
# 2. Key Vault
# The name carries a random suffix, so an existing vault has to be discovered
# rather than recomputed - regenerating the suffix would strand every secret.
# ---------------------------------------------------------------------
KEYVAULT_NAME="${KEYVAULT_NAME:-$(az keyvault list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[?starts_with(name, 'kv-sovereignshield')].name | [0]" -o tsv 2>/dev/null || true)}"

if [ -n "$KEYVAULT_NAME" ]; then
  echo "[skip]   Key Vault $KEYVAULT_NAME already exists."
else
  KEYVAULT_NAME="kv-sovereignshield-$RANDOM"
  echo "[create] Key Vault $KEYVAULT_NAME"
  az keyvault create \
    --name "$KEYVAULT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --enable-rbac-authorization false \
    --output none
fi

# ---------------------------------------------------------------------
# 3. CI/CD service principal
# ---------------------------------------------------------------------
CICD_APP_ID="$(app_id_for "$CICD_SPN_NAME")"
CICD_SECRET=""
CICD_TENANT=""

if [ -n "$CICD_APP_ID" ]; then
  echo "[skip]   $CICD_SPN_NAME already exists ($CICD_APP_ID)."
else
  echo "[create] $CICD_SPN_NAME"
  SPN_JSON=$(az ad sp create-for-rbac --name "$CICD_SPN_NAME" --output json)
  CICD_APP_ID=$(echo "$SPN_JSON" | jq -r '.appId')
  CICD_SECRET=$(echo "$SPN_JSON" | jq -r '.password')
  CICD_TENANT=$(echo "$SPN_JSON" | jq -r '.tenant')
fi

if secret_exists "$KEYVAULT_NAME" "spn-client-secret"; then
  echo "[skip]   CI/CD credentials already stored in $KEYVAULT_NAME."
else
  if [ -z "$CICD_SECRET" ]; then
    # The app predates the vault entry, so a fresh credential is the only way to
    # populate it: the original password is unrecoverable by design.
    echo "[create] CI/CD credential (app exists, no stored secret)"
    CICD_SECRET=$(az ad app credential reset --id "$CICD_APP_ID" --append --query password -o tsv)
    CICD_TENANT=$(az account show --query tenantId -o tsv)
  fi
  az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-client-id"     --value "$CICD_APP_ID" --output none
  az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-client-secret" --value "$CICD_SECRET" --output none
  az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "spn-tenant-id"     --value "$CICD_TENANT" --output none
  echo "[create] CI/CD credentials stored in $KEYVAULT_NAME."
fi

# ---------------------------------------------------------------------
# 4. Public portal proxy service principal
#
# The identity every unauthenticated portal request runs as. Created WITHOUT
# any Azure RBAC role assignment - create-for-rbac would grant it Contributor
# over the subscription, and this principal has no business touching the
# control plane. Its entire entitlement is the Unity Catalog row filter
# attached to sg-sovereignshield-public: published, free-to-publish rows.
# ---------------------------------------------------------------------
PUBLIC_APP_ID="$(app_id_for "$PUBLIC_SPN_NAME")"

if [ -n "$PUBLIC_APP_ID" ]; then
  echo "[skip]   $PUBLIC_SPN_NAME already exists ($PUBLIC_APP_ID)."
else
  echo "[create] $PUBLIC_SPN_NAME"
  PUBLIC_APP_ID=$(az ad app create --display-name "$PUBLIC_SPN_NAME" --query appId -o tsv)
fi

if az ad sp show --id "$PUBLIC_APP_ID" >/dev/null 2>&1; then
  echo "[skip]   Service principal for $PUBLIC_SPN_NAME already exists."
else
  echo "[create] Service principal for $PUBLIC_SPN_NAME"
  az ad sp create --id "$PUBLIC_APP_ID" --output none
fi

if secret_exists "$KEYVAULT_NAME" "public-spn-client-secret"; then
  echo "[skip]   Public proxy credentials already stored in $KEYVAULT_NAME."
else
  echo "[create] Public proxy credential"
  PUBLIC_SECRET=$(az ad app credential reset --id "$PUBLIC_APP_ID" --append --query password -o tsv)
  az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "public-spn-client-id"     --value "$PUBLIC_APP_ID" --output none
  az keyvault secret set --vault-name "$KEYVAULT_NAME" --name "public-spn-client-secret" --value "$PUBLIC_SECRET" --output none
fi

# ---------------------------------------------------------------------
# 5. Public tier group membership
# The group belongs to grp_users_create.sh, which may not have run yet.
# ---------------------------------------------------------------------
PUBLIC_OBJECT_ID=$(az ad sp show --id "$PUBLIC_APP_ID" --query id -o tsv)

if az ad group show --group "$PUBLIC_GROUP_NAME" >/dev/null 2>&1; then
  if [ "$(az ad group member check --group "$PUBLIC_GROUP_NAME" --member-id "$PUBLIC_OBJECT_ID" --query value -o tsv)" = "true" ]; then
    echo "[skip]   $PUBLIC_SPN_NAME already in $PUBLIC_GROUP_NAME."
  else
    echo "[create] Adding $PUBLIC_SPN_NAME to $PUBLIC_GROUP_NAME"
    az ad group member add --group "$PUBLIC_GROUP_NAME" --member-id "$PUBLIC_OBJECT_ID" --output none
  fi
else
  echo "[warn]   $PUBLIC_GROUP_NAME does not exist yet - run sh/grp_users_create.sh, then re-run this script."
fi

echo
echo "========================================================"
echo "Key Vault Name      : $KEYVAULT_NAME"
echo "CI/CD App ID        : $CICD_APP_ID"
echo "Public Proxy App ID : $PUBLIC_APP_ID"
echo "========================================================"
echo "pre_auth.ps1 discovers the vault automatically; no edit required."
echo
echo "Next: add both service principals to the Databricks ACCOUNT and confirm"
echo "their group membership, otherwise the row filter fails closed and the"
echo "portal shows nothing. See sh/databricks_account_setup.ps1."
