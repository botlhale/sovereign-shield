#!/bin/bash
# =====================================================================
# Provisions the Entra ID persona layer: five security groups, four test
# users, and their memberships.
#
# IDEMPOTENT. Existing groups and users are reused rather than recreated, so
# this can be re-run after a workspace teardown to add only what is missing.
# An existing user's password is never reset - that would invalidate a login
# someone may already be using.
# =====================================================================

set -euo pipefail

TENANT_DOMAIN="${TENANT_DOMAIN:-13668754CANADAINC.onmicrosoft.com}"

# Only consulted when a user genuinely has to be created.
TEMP_PASSWORD="${TEMP_PASSWORD:-Fe301A@Mat5helo}"

# display-name : mail-nickname
GROUPS=(
  "sg-sovereignshield-admin:sg-ss-admin"
  "sg-sovereignshield-submitter-ca:sg-ss-sub-ca"
  "sg-sovereignshield-submitter-us:sg-ss-sub-us"
  "sg-sovereignshield-researchers:sg-ss-research"
  # Holds no humans: its only member is the portal's proxy service principal,
  # added by kv_spn_create.sh. Without this group the row filter's fail-closed
  # default returns zero rows to every anonymous visitor.
  "sg-sovereignshield-public:sg-ss-public"
)

# upn-prefix : display name : group
USERS=(
  "admin_lead:Admin Lead:sg-sovereignshield-admin"
  "boc_analyst:BOC Analyst:sg-sovereignshield-submitter-ca"
  "fed_analyst:Fed Analyst:sg-sovereignshield-submitter-us"
  "econ_researcher:Econ Researcher:sg-sovereignshield-researchers"
)

ensure_group() {
  local display="$1" nickname="$2" existing
  existing=$(az ad group list --display-name "$display" --query "[0].id" -o tsv 2>/dev/null || true)
  if [ -n "$existing" ]; then
    echo "[skip]   Group $display exists." >&2
    echo "$existing"
  else
    echo "[create] Group $display" >&2
    az ad group create --display-name "$display" --mail-nickname "$nickname" --query id -o tsv
  fi
}

ensure_user() {
  local upn="$1" display="$2" existing
  existing=$(az ad user list --filter "userPrincipalName eq '$upn'" --query "[0].id" -o tsv 2>/dev/null || true)
  if [ -n "$existing" ]; then
    echo "[skip]   User $upn exists." >&2
    echo "$existing"
  else
    echo "[create] User $upn" >&2
    az ad user create \
      --display-name "$display" \
      --user-principal-name "$upn" \
      --password "$TEMP_PASSWORD" \
      --query id -o tsv
  fi
}

ensure_member() {
  local group="$1" member_id="$2" label="$3"
  if [ "$(az ad group member check --group "$group" --member-id "$member_id" --query value -o tsv 2>/dev/null || echo false)" = "true" ]; then
    echo "[skip]   $label already in $group."
  else
    echo "[create] Adding $label to $group"
    az ad group member add --group "$group" --member-id "$member_id" --output none
  fi
}

echo "=== Entra ID groups ==="
for entry in "${GROUPS[@]}"; do
  ensure_group "${entry%%:*}" "${entry##*:}" >/dev/null
done

echo
echo "=== Entra ID users and memberships ==="
for entry in "${USERS[@]}"; do
  IFS=":" read -r prefix display group <<< "$entry"
  upn="$prefix@$TENANT_DOMAIN"
  user_id=$(ensure_user "$upn" "$display")
  ensure_member "$group" "$user_id" "$upn"
done

echo
echo "=== Pipeline service principal membership ==="
# Ownership does not exempt a principal from a row filter. The SCD2 engine reads
# the history table to find records to expire; if the filter hid those rows the
# merge would treat every row as new and silently duplicate history.
CICD_APP_ID=$(az ad app list --display-name "spn-sovereignshield-cicd" \
  --query "[?displayName=='spn-sovereignshield-cicd'].appId | [0]" -o tsv 2>/dev/null || true)

if [ -n "$CICD_APP_ID" ]; then
  CICD_OBJECT_ID=$(az ad sp show --id "$CICD_APP_ID" --query id -o tsv)
  ensure_member "sg-sovereignshield-admin" "$CICD_OBJECT_ID" "spn-sovereignshield-cicd"
else
  echo "[warn]   spn-sovereignshield-cicd not found - run sh/kv_spn_create.sh first."
fi

echo
echo "Zero-Trust Identity Layer Provisioned Successfully."
echo "Remember: these groups must also exist at the Databricks ACCOUNT level"
echo "before is_account_group_member() can resolve them inside Unity Catalog."
echo "Run sh/databricks_account_setup.ps1 next."
