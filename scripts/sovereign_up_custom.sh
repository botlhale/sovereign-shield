#!/usr/bin/env bash
# =====================================================================
# Attach Sovereign Shield to an existing Azure and Databricks estate.
#
# Every resource is looked up first. Existing resources are attached and never
# modified, re-tagged or re-created; only the missing delta is provisioned. Each
# created resource carries ManagedBy=SovereignShield and ProvisionedScope=Delta as
# tags (metadata on the container, comments on Unity Catalog objects), and
# everything attached or created is written to the provisioning manifest that
# scripts/sovereign_down_custom.sh reads for surgical teardown.
#
# Requires: az (logged in), jq, the Databricks CLI and, for the policy plane, the
# repository Python environment. No secret is read, prompted for or stored.
# =====================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${REPO_ROOT}/.sovereign_provisioned_manifest.json"
TAGS=(ManagedBy=SovereignShield ProvisionedScope=Delta)
TAG_COMMENT="ManagedBy=SovereignShield; ProvisionedScope=Delta"
# Fixed: the policy SQL, bundle and gateway all address this catalog.
CATALOG="dbw_sovereignshield"
SCHEMAS=(sovereign_shield sovereign_intake sovereign_submissions)
PERSONA_GROUPS=(sg-sovereignshield-admin sg-sovereignshield-researchers sg-sovereignshield-submitter-ca
                sg-sovereignshield-submitter-us sg-sovereignshield-public)

SUBSCRIPTION="" RESOURCE_GROUP="" LOCATION="" WORKSPACE_NAME="" WORKSPACE_URL="" KEY_VAULT=""
STORAGE_ACCOUNT="" METASTORE_ID="" REQUESTED_WAREHOUSE_ID="" CONTAINER="sovereignshield"
ACCESS_CONNECTOR="dbac-sovereignshield" STORAGE_CREDENTIAL="sc_sovereignshield"
EXTERNAL_LOCATION="el_sovereignshield" WAREHOUSE_NAME="sovereignshield-warehouse"
GRANTS="auto" SKIP_POLICIES=0 ADOPT_POLICY_OBJECTS=0 INTERACTIVE=1 ASSUME_YES=0 PLAN_ONLY=0 DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/sovereign_up_custom.sh [options]

Existing infrastructure (prompted for when omitted in an interactive terminal):
  --subscription ID          Azure subscription (default: current az account)
  --resource-group NAME      Resource group to attach, or create if missing
  --location REGION          Region for created resources (default: resource group's)
  --workspace-name NAME      Databricks workspace in the resource group
  --workspace-url HOST       Existing workspace URL instead of a name (any resource group)
  --key-vault NAME           Key Vault to attach, or create if missing
  --storage-account NAME     ADLS Gen2 account for Unity Catalog storage
  --metastore-id ID          Expected Unity Catalog metastore (never created here)

Optional names: --container, --access-connector, --storage-credential,
  --external-location, --warehouse-id (attach) or --warehouse-name (find/create)

Behaviour:
  --grants auto|always|never  Apply persona grants. auto: only when this run created the
                              catalog and every persona group exists (default auto)
  --skip-policies             Provision infrastructure only; do not apply the policy plane
  --adopt-policy-objects      Rebind masks and filters on, and replace, existing protected
                              tables and the published view this script did not create.
                              Teardown keeps them and does not restore their prior state
  --manifest PATH             Default: .sovereign_provisioned_manifest.json in the repo root
  --dry-run                   Show what would be attached or created; change nothing
  --non-interactive           Never prompt; fail on missing required values
  -y, --yes                   Do not ask for confirmation before creating resources
EOF
}

log() { printf '\n==> %s\n' "$*" >&2; }
note() { printf '    %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# One checkout-level lock, shared with sh/sovereignshield_up.ps1 and _down.ps1, keeps
# provisioning and teardown from interleaving manifest updates. It is released on exit.
acquire_lifecycle_lock() {
  local directory="${REPO_ROOT}/.pytest_cache"
  mkdir -p "$directory"
  exec 9>>"${directory}/sovereignshield.lifecycle.lock"
  if command -v flock >/dev/null; then
    flock -n 9
  else
    perl -MFcntl=:flock -e 'open(my $lock, ">&=", 9) or exit 1; flock($lock, LOCK_EX | LOCK_NB) or exit 1'
  fi || die "Another lifecycle operation holds this checkout's lock."
}

while (($#)); do
  case "$1" in
    --subscription) SUBSCRIPTION="$2"; shift 2 ;;
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --location) LOCATION="$2"; shift 2 ;;
    --workspace-name) WORKSPACE_NAME="$2"; shift 2 ;;
    --workspace-url) WORKSPACE_URL="$2"; shift 2 ;;
    --key-vault) KEY_VAULT="$2"; shift 2 ;;
    --storage-account) STORAGE_ACCOUNT="$2"; shift 2 ;;
    --metastore-id) METASTORE_ID="$2"; shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    --access-connector) ACCESS_CONNECTOR="$2"; shift 2 ;;
    --storage-credential) STORAGE_CREDENTIAL="$2"; shift 2 ;;
    --external-location) EXTERNAL_LOCATION="$2"; shift 2 ;;
    --warehouse-id) REQUESTED_WAREHOUSE_ID="$2"; shift 2 ;;
    --warehouse-name) WAREHOUSE_NAME="$2"; shift 2 ;;
    --grants) GRANTS="$2"; shift 2 ;;
    --skip-policies) SKIP_POLICIES=1; shift ;;
    --adopt-policy-objects) ADOPT_POLICY_OBJECTS=1; shift ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --dry-run) PLAN_ONLY=1; shift ;;
    --non-interactive) INTERACTIVE=0; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done
[[ "$GRANTS" =~ ^(auto|always|never)$ ]] || die "--grants must be auto, always or never."
[[ -t 0 ]] || INTERACTIVE=0

for tool in az jq databricks; do
  command -v "$tool" >/dev/null || die "$tool is required on PATH."
done
acquire_lifecycle_lock

ask() {
  local variable="$1" question="$2" default="${3:-}" answer
  [[ -n "${!variable}" ]] && return 0
  if ((INTERACTIVE)); then
    read -r -p "$question${default:+ [$default]}: " answer
    printf -v "$variable" '%s' "${answer:-$default}"
  else
    printf -v "$variable" '%s' "$default"
  fi
}

current_subscription="$(az account show --query id -o tsv 2>/dev/null)" || die "Run az login first."
ask SUBSCRIPTION "Azure subscription ID" "$current_subscription"
ask RESOURCE_GROUP "Resource group (existing or new)"
if [[ -z "$WORKSPACE_NAME" && -z "$WORKSPACE_URL" ]]; then
  ask WORKSPACE_URL "Existing Databricks workspace URL (blank to give a name)"
  [[ -n "$WORKSPACE_URL" ]] || ask WORKSPACE_NAME "Databricks workspace name (existing or new)"
fi
ask KEY_VAULT "Key Vault name (existing or new)"
ask STORAGE_ACCOUNT "ADLS Gen2 storage account name (existing or new)"
ask METASTORE_ID "Expected Unity Catalog metastore ID (blank: the workspace's assigned metastore)"
for required in SUBSCRIPTION RESOURCE_GROUP KEY_VAULT STORAGE_ACCOUNT; do
  flag="${required,,}"
  [[ -n "${!required}" ]] || die "--${flag//_/-} is required."
done
[[ -n "$WORKSPACE_NAME$WORKSPACE_URL" ]] || die "--workspace-name or --workspace-url is required."
az account set --subscription "$SUBSCRIPTION"
az extension add --name databricks --upgrade --only-show-errors >/dev/null
unset DATABRICKS_TOKEN DATABRICKS_CLIENT_ID DATABRICKS_CLIENT_SECRET DATABRICKS_CONFIG_PROFILE ARM_CLIENT_ID ARM_CLIENT_SECRET

# ---------------------------------------------------------------------
# Manifest: provenance is sticky, so a rerun never relabels what this script created.
# ---------------------------------------------------------------------
manifest_update() {
  ((DRY_RUN)) && return 0
  local temporary
  temporary="$(mktemp "${MANIFEST}.XXXXXX")"
  jq "$@" "$MANIFEST" >"$temporary" && mv "$temporary" "$MANIFEST"
}

manifest_init() {
  ((DRY_RUN)) && return 0
  if [[ ! -f "$MANIFEST" ]]; then
    (umask 077 && jq -n --arg subscription "$SUBSCRIPTION" --arg now "$(now)" \
      '{schema_version: 1, project: "SovereignShield", subscription_id: $subscription, created_at: $now,
        updated_at: $now, tags: {ManagedBy: "SovereignShield", ProvisionedScope: "Delta"}, resources: []}' >"$MANIFEST")
  fi
  [[ "$(jq -r .subscription_id "$MANIFEST")" == "$SUBSCRIPTION" ]] ||
    die "$MANIFEST belongs to another subscription; pass --manifest for this estate."
}

record() {
  manifest_update --arg kind "$1" --arg name "$2" --arg id "$3" --argjson pre "$4" --arg now "$(now)" '
    .updated_at = $now
    | if any(.resources[]; .kind == $kind and .name == $name and .deleted_at == null)
      then .resources |= map(if .kind == $kind and .name == $name and .deleted_at == null and $id != ""
                             then .id = $id else . end)
      else .resources += [{kind: $kind, name: $name, id: $id, pre_existing: $pre, recorded_at: $now}]
      end'
}

attach() { note "attach  $1 $2"; record "$1" "$2" "$3" true; }

owned() {
  [[ -f "$MANIFEST" ]] && jq -e --arg kind "$1" --arg name "$2" \
    'any(.resources[]; .kind == $kind and .name == $name and .deleted_at == null and .pre_existing == false)' \
    "$MANIFEST" >/dev/null
}

create() {
  local kind="$1" name="$2" json
  shift 2
  if ((DRY_RUN)); then
    note "create  $kind $name"
    printf '{"id":"planned/%s","name":"%s"}' "$kind" "$name"
    return 0
  fi
  note "create  $kind $name"
  json="$("$@")"
  record "$kind" "$name" "$(jq -r '.id // .full_name // .name // .metastore_id // empty' <<<"$json")" false
  printf '%s' "$json"
}

retry() {
  local attempt
  for attempt in 1 2 3 4 5 6; do
    "$@" && return 0
    ((attempt < 6)) && { note "waiting for role propagation (attempt $attempt)"; sleep "${SOVEREIGN_RETRY_SECONDS:-30}"; }
  done
  return 1
}

need_location() { [[ -n "$LOCATION" ]] || die "--location is required to create $1."; }

# Sets FOUND and succeeds when the object exists; fails only on a confirmed not-found. Any other error
# (expired login, throttling, outage) aborts, so an existing resource is never created or relabelled.
FOUND=""
lookup() {
  local error
  error="$(mktemp)"
  if FOUND="$("$@" 2>"$error")"; then
    rm -f "$error"
    return 0
  fi
  if grep -qiE 'not[ _]?found|not be found|does not exist|RESOURCE_DOES_NOT_EXIST' "$error"; then
    rm -f "$error"
    return 1
  fi
  printf 'ERROR: could not tell whether this exists, so nothing more was changed: %s\n' "$*" >&2
  cat "$error" >&2
  rm -f "$error"
  exit 1
}

# ---------------------------------------------------------------------
# Azure control plane
# ---------------------------------------------------------------------
provision_azure() {
  local json principal assignment
  log "Azure resources in subscription $SUBSCRIPTION"
  if lookup az group show --name "$RESOURCE_GROUP" -o json; then
    json="$FOUND"
    attach resource_group "$RESOURCE_GROUP" "$(jq -r .id <<<"$json")"
    [[ -n "$LOCATION" ]] || LOCATION="$(jq -r .location <<<"$json")"
  else
    need_location "resource group $RESOURCE_GROUP"
    create resource_group "$RESOURCE_GROUP" az group create --name "$RESOURCE_GROUP" --location "$LOCATION" \
      --tags "${TAGS[@]}" -o json >/dev/null
  fi

  if lookup az keyvault show --name "$KEY_VAULT" -o json; then
    attach key_vault "$KEY_VAULT" "$(jq -r .id <<<"$FOUND")"
  else
    need_location "Key Vault $KEY_VAULT"
    create key_vault "$KEY_VAULT" az keyvault create --name "$KEY_VAULT" --resource-group "$RESOURCE_GROUP" \
      --location "$LOCATION" --enable-rbac-authorization true --enable-purge-protection true \
      --tags "${TAGS[@]}" -o json >/dev/null
  fi

  if lookup az storage account show --name "$STORAGE_ACCOUNT" -o json; then
    json="$FOUND"
    [[ "$(jq -r '.isHnsEnabled // false' <<<"$json")" == true ]] ||
      die "Storage account $STORAGE_ACCOUNT exists without a hierarchical namespace; Unity Catalog needs ADLS Gen2."
    attach storage_account "$STORAGE_ACCOUNT" "$(jq -r .id <<<"$json")"
  else
    need_location "storage account $STORAGE_ACCOUNT"
    json="$(create storage_account "$STORAGE_ACCOUNT" az storage account create --name "$STORAGE_ACCOUNT" \
      --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --sku Standard_LRS --kind StorageV2 --hns true \
      --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false \
      --tags "${TAGS[@]}" -o json)"
  fi
  STORAGE_ID="$(jq -r .id <<<"$json")"

  if [[ "$STORAGE_ID" != planned/* ]] &&
    lookup az storage container-rm show --storage-account "$STORAGE_ID" --name "$CONTAINER" -o json; then
    attach storage_container "$STORAGE_ACCOUNT/$CONTAINER" "$(jq -r .id <<<"$FOUND")"
  else
    create storage_container "$STORAGE_ACCOUNT/$CONTAINER" az storage container-rm create \
      --storage-account "$STORAGE_ID" --name "$CONTAINER" --metadata "${TAGS[@]}" -o json >/dev/null
  fi

  if [[ -n "$WORKSPACE_URL" ]]; then
    local host="${WORKSPACE_URL#https://}"
    host="${host%%/*}"
    json="$(az databricks workspace list -o json | jq -c --arg host "$host" '[.[] | select(.workspaceUrl == $host)][0] // empty')"
    [[ -n "$json" ]] || die "No workspace with URL $host is visible in subscription $SUBSCRIPTION."
    WORKSPACE_NAME="$(jq -r .name <<<"$json")"
    attach databricks_workspace "$WORKSPACE_NAME" "$(jq -r .id <<<"$json")"
  elif lookup az databricks workspace show --resource-group "$RESOURCE_GROUP" --name "$WORKSPACE_NAME" -o json; then
    json="$FOUND"
    attach databricks_workspace "$WORKSPACE_NAME" "$(jq -r .id <<<"$json")"
  else
    need_location "workspace $WORKSPACE_NAME"
    json="$(create databricks_workspace "$WORKSPACE_NAME" az databricks workspace create --name "$WORKSPACE_NAME" \
      --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --sku premium --tags "${TAGS[@]}" -o json)"
  fi
  if ((!DRY_RUN)) || [[ "$(jq -r .id <<<"$json")" != planned/* ]]; then
    [[ "$(jq -r '.sku.name // "premium"' <<<"$json")" == premium ]] ||
      die "Row filters and column masks need a Premium workspace; $WORKSPACE_NAME is $(jq -r .sku.name <<<"$json")."
    WORKSPACE_HOST="$(jq -r '.workspaceUrl // empty' <<<"$json")"
  else
    WORKSPACE_HOST=""
  fi

  if lookup az databricks access-connector show --resource-group "$RESOURCE_GROUP" --name "$ACCESS_CONNECTOR" -o json; then
    json="$FOUND"
    attach access_connector "$ACCESS_CONNECTOR" "$(jq -r .id <<<"$json")"
  else
    need_location "access connector $ACCESS_CONNECTOR"
    json="$(create access_connector "$ACCESS_CONNECTOR" az databricks access-connector create \
      --resource-group "$RESOURCE_GROUP" --name "$ACCESS_CONNECTOR" --location "$LOCATION" \
      --identity-type SystemAssigned --tags "${TAGS[@]}" -o json)"
  fi
  CONNECTOR_ID="$(jq -r .id <<<"$json")"
  principal="$(jq -r '.identity.principalId // empty' <<<"$json")"

  if [[ -z "$principal" || "$STORAGE_ID" == planned/* ]]; then
    ((DRY_RUN)) || die "Access connector $ACCESS_CONNECTOR has no system-assigned identity."
    create role_assignment "$ACCESS_CONNECTOR->$STORAGE_ACCOUNT" >/dev/null
  else
    assignment="$(az role assignment list --assignee "$principal" --scope "$STORAGE_ID" \
      --role "Storage Blob Data Contributor" -o json | jq -r '.[0].id // empty')"
    if [[ -n "$assignment" ]]; then
      attach role_assignment "$ACCESS_CONNECTOR->$STORAGE_ACCOUNT" "$assignment"
    else
      create role_assignment "$ACCESS_CONNECTOR->$STORAGE_ACCOUNT" az role assignment create \
        --assignee-object-id "$principal" --assignee-principal-type ServicePrincipal \
        --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" -o json >/dev/null
    fi
  fi
}

# ---------------------------------------------------------------------
# Unity Catalog and SQL warehouse
# ---------------------------------------------------------------------
provision_databricks() {
  local json schema root group
  if [[ -z "$WORKSPACE_HOST" ]]; then
    note "Unity Catalog objects are planned once the workspace exists."
    return 0
  fi
  export DATABRICKS_HOST="https://$WORKSPACE_HOST" DATABRICKS_AUTH_TYPE=azure-cli
  log "Unity Catalog on $WORKSPACE_HOST"
  manifest_update --arg host "$WORKSPACE_HOST" '.workspace_host = $host'

  json="$(databricks metastores current -o json 2>/dev/null)" ||
    die "The workspace has no Unity Catalog metastore. Assigning one is an account-administrator decision outside this script."
  local metastore
  metastore="$(jq -r .metastore_id <<<"$json")"
  [[ -z "$METASTORE_ID" || "$METASTORE_ID" == "$metastore" ]] ||
    die "The workspace uses metastore $metastore, not the expected $METASTORE_ID."
  attach metastore "$metastore" "$metastore"

  if lookup databricks storage-credentials get "$STORAGE_CREDENTIAL" -o json; then
    attach storage_credential "$STORAGE_CREDENTIAL" "$(jq -r '.id // .name' <<<"$FOUND")"
  else
    create storage_credential "$STORAGE_CREDENTIAL" databricks storage-credentials create -o json --json "$(jq -nc \
      --arg name "$STORAGE_CREDENTIAL" --arg connector "$CONNECTOR_ID" --arg comment "$TAG_COMMENT" \
      '{name: $name, azure_managed_identity: {access_connector_id: $connector}, comment: $comment}')" >/dev/null
  fi

  if lookup databricks external-locations get "$EXTERNAL_LOCATION" -o json; then
    json="$FOUND"
    attach external_location "$EXTERNAL_LOCATION" "$(jq -r '.id // .name' <<<"$json")"
  else
    json="$(create external_location "$EXTERNAL_LOCATION" retry databricks external-locations create \
      "$EXTERNAL_LOCATION" "abfss://$CONTAINER@$STORAGE_ACCOUNT.dfs.core.windows.net/" "$STORAGE_CREDENTIAL" \
      --comment "$TAG_COMMENT" -o json)"
  fi
  root="$(jq -r '.url // empty' <<<"$json")"
  root="${root:-abfss://$CONTAINER@$STORAGE_ACCOUNT.dfs.core.windows.net/}"

  if lookup databricks catalogs get "$CATALOG" -o json; then
    attach catalog "$CATALOG" "$CATALOG"
    CATALOG_CREATED=0
  else
    create catalog "$CATALOG" databricks catalogs create "$CATALOG" --storage-root "${root%/}/$CATALOG" \
      --comment "$TAG_COMMENT" -o json >/dev/null
    CATALOG_CREATED=1
  fi

  for schema in "${SCHEMAS[@]}"; do
    if lookup databricks schemas get "$CATALOG.$schema" -o json; then
      attach schema "$CATALOG.$schema" "$CATALOG.$schema"
    else
      create schema "$CATALOG.$schema" databricks schemas create "$schema" "$CATALOG" --comment "$TAG_COMMENT" -o json >/dev/null
    fi
  done

  if lookup databricks volumes read "$CATALOG.sovereign_submissions.submissions" -o json; then
    attach volume "$CATALOG.sovereign_submissions.submissions" "$CATALOG.sovereign_submissions.submissions"
  else
    create volume "$CATALOG.sovereign_submissions.submissions" databricks volumes create "$CATALOG" \
      sovereign_submissions submissions MANAGED --comment "$TAG_COMMENT" -o json >/dev/null
  fi

  if [[ -n "$REQUESTED_WAREHOUSE_ID" ]]; then
    WAREHOUSE_ID="$REQUESTED_WAREHOUSE_ID"
    json="$(databricks warehouses get "$WAREHOUSE_ID" -o json)" || die "SQL warehouse $WAREHOUSE_ID was not found."
    attach sql_warehouse "$(jq -r .name <<<"$json")" "$WAREHOUSE_ID"
  else
    json="$(databricks warehouses list -o json | jq -c --arg name "$WAREHOUSE_NAME" '[.[] | select(.name == $name)][0] // empty')"
    if [[ -n "$json" ]]; then
      attach sql_warehouse "$WAREHOUSE_NAME" "$(jq -r .id <<<"$json")"
    else
      json="$(create sql_warehouse "$WAREHOUSE_NAME" databricks warehouses create --no-wait -o json --json "$(jq -nc \
        --arg name "$WAREHOUSE_NAME" '{name: $name, cluster_size: "2X-Small", min_num_clusters: 1, max_num_clusters: 1,
          auto_stop_mins: 10, enable_serverless_compute: true, warehouse_type: "PRO",
          tags: {custom_tags: [{key: "ManagedBy", value: "SovereignShield"}, {key: "ProvisionedScope", value: "Delta"}]}}')")"
    fi
    WAREHOUSE_ID="$(jq -r .id <<<"$json")"
  fi

  MISSING_GROUPS=()
  json="$(databricks groups list -o json 2>/dev/null || echo '[]')"
  for group in "${PERSONA_GROUPS[@]}"; do
    jq -e --arg group "$group" 'any(.[]; .displayName == $group)' <<<"$json" >/dev/null || MISSING_GROUPS+=("$group")
  done
  ((${#MISSING_GROUPS[@]} == 0)) ||
    note "missing persona groups (policies fail closed for them): ${MISSING_GROUPS[*]}"
}

# ---------------------------------------------------------------------
# Policy plane: content-addressed functions, protected tables, verified bindings
# ---------------------------------------------------------------------
provision_policies() {
  local python="$REPO_ROOT/.venv/bin/python" result status=0 grant_flag=() policy_flags=() name
  ((SKIP_POLICIES)) && { note "policy plane skipped (--skip-policies)"; return 0; }
  [[ -n "$WORKSPACE_HOST" ]] || { note "policy plane is planned once the workspace exists."; return 0; }
  case "$GRANTS" in
    always) ;;
    never) grant_flag=(--skip-grants) ;;
    auto) { ((CATALOG_CREATED)) || owned catalog "$CATALOG"; } && ((${#MISSING_GROUPS[@]} == 0)) || grant_flag=(--skip-grants) ;;
  esac
  log "Policy plane through SQL warehouse $WAREHOUSE_ID${grant_flag:+ (grants skipped)}"
  if ((DRY_RUN)); then
    note "apply   triple-lock functions, protected tables and bindings"
    return 0
  fi
  [[ -x "$python" ]] || python="$(command -v python3)"
  ((ADOPT_POLICY_OBJECTS)) && policy_flags+=(--adopt-existing)
  while read -r name; do
    policy_flags+=(--owned "$name")
  done < <(jq -r '.resources[] | select(.deleted_at == null and .pre_existing == false
                                         and (.kind == "table" or .kind == "view")) | .name' "$MANIFEST")
  result="$(mktemp)"
  "$python" "$REPO_ROOT/scripts/apply_policies.py" --host "$WORKSPACE_HOST" --warehouse-id "$WAREHOUSE_ID" \
    --result "$result" "${grant_flag[@]}" "${policy_flags[@]}" || status=$?
  while read -r item; do
    record "$(jq -r .kind <<<"$item")" "$(jq -r .name <<<"$item")" "$(jq -r .name <<<"$item")" \
      "$(jq -r .pre_existing <<<"$item")"
  done < <(jq -c '.[]' "$result")
  rm -f "$result"
  ((status == 0)) || die "Policy application failed; what it created is recorded for teardown. Fix the cause and rerun."
}

provision() {
  CATALOG_CREATED=0 MISSING_GROUPS=() STORAGE_ID="" CONNECTOR_ID="" WORKSPACE_HOST="" WAREHOUSE_ID=""
  manifest_init
  provision_azure
  provision_databricks
  provision_policies
}

DRY_RUN=1
provision
((PLAN_ONLY)) && { log "Dry run complete; nothing was changed."; exit 0; }
if ((!ASSUME_YES)); then
  ((INTERACTIVE)) || die "Refusing to create resources without confirmation; rerun with --yes."
  read -r -p "Create the planned resources and record them in $MANIFEST? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || die "Cancelled; nothing was changed."
fi
DRY_RUN=0
provision

log "Provisioning manifest: $MANIFEST"
jq -r '.resources[] | select(.deleted_at == null)
       | [(if .pre_existing then "attached" else "created " end), .kind, .name] | @tsv' "$MANIFEST" >&2
note "Teardown removes only 'created' entries: scripts/sovereign_down_custom.sh --manifest $MANIFEST"
