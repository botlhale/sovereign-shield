#!/usr/bin/env bash
# =====================================================================
# Surgical teardown for scripts/sovereign_up_custom.sh.
#
# Reads the provisioning manifest and removes only the resources it records as
# created by Sovereign Shield, in reverse dependency order. Attached, pre-existing
# resources (resource groups, workspaces, metastores, shared vaults or storage) are
# never touched. Before the first deletion, every created Azure resource must still
# carry ManagedBy=SovereignShield (a container as metadata, since it cannot be
# tagged); a changed or missing marker means someone else may rely on it and on
# what was built on it, so nothing is deleted.
# Schemas and catalogs are dropped without force: anything added since stays.
# An object counts as gone, and its manifest entry closes, only once the CLI
# reports it missing; the first object kept or not confirmed gone stops the
# teardown, so nothing beneath it is removed.
# =====================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${REPO_ROOT}/.sovereign_provisioned_manifest.json"
ASSUME_YES=0 PLAN_ONLY=0
ORDER=(view table function volume schema catalog external_location storage_credential sql_warehouse
       role_assignment access_connector databricks_workspace storage_container storage_account key_vault
       resource_group)

usage() {
  cat <<'EOF'
Usage: scripts/sovereign_down_custom.sh [--manifest PATH] [--dry-run] [--yes]

  --manifest PATH   Default: .sovereign_provisioned_manifest.json in the repository root
  --dry-run         Show the teardown plan; change nothing
  -y, --yes         Skip the typed confirmation (for reviewed automation)
EOF
}

note() { printf '    %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

while (($#)); do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --dry-run) PLAN_ONLY=1; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done

for tool in az jq databricks; do
  command -v "$tool" >/dev/null || die "$tool is required on PATH."
done
[[ -f "$MANIFEST" ]] || die "No manifest at $MANIFEST: nothing is recorded as created by Sovereign Shield."

SUBSCRIPTION="$(jq -r .subscription_id "$MANIFEST")"
WORKSPACE_HOST="$(jq -r '.workspace_host // empty' "$MANIFEST")"
az account set --subscription "$SUBSCRIPTION"
unset DATABRICKS_TOKEN DATABRICKS_CLIENT_ID DATABRICKS_CLIENT_SECRET DATABRICKS_CONFIG_PROFILE ARM_CLIENT_ID ARM_CLIENT_SECRET
[[ -z "$WORKSPACE_HOST" ]] || export DATABRICKS_HOST="https://$WORKSPACE_HOST" DATABRICKS_AUTH_TYPE=azure-cli

order_json="$(printf '%s\n' "${ORDER[@]}" | jq -R . | jq -sc .)"
plan="$(jq -c --argjson order "$order_json" '
  [.resources[] | select(.deleted_at == null and .pre_existing == false)
   | . as $resource | . + {rank: (($order | index($resource.kind)) // 99)}] | sort_by(.rank) | .[]' "$MANIFEST")"
keep="$(jq -r '.resources[] | select(.deleted_at == null and .pre_existing == true) | "KEEP    \(.kind) \(.name) (pre-existing)"' "$MANIFEST")"

printf '\nSovereign Shield teardown for subscription %s\n' "$SUBSCRIPTION" >&2
[[ -z "$plan" ]] || jq -r '"DELETE  \(.kind) \(.name)"' <<<"$plan" >&2
[[ -z "$keep" ]] || printf '%s\n' "$keep" >&2
printf '%s\n' "NEVER   metastores, human identities and anything absent from the manifest" >&2
[[ -n "$plan" ]] || { note "Nothing recorded as created remains."; exit 0; }

mark_deleted() {
  local temporary
  temporary="$(mktemp "${MANIFEST}.XXXXXX")"
  jq --arg kind "$1" --arg name "$2" --arg now "$(now)" '
    .updated_at = $now
    | .resources |= map(if .kind == $kind and .name == $name and .deleted_at == null then .deleted_at = $now else . end)' \
    "$MANIFEST" >"$temporary" && mv "$temporary" "$MANIFEST"
}

# Containers cannot be tagged, so they carry the marker as metadata.
still_tagged() {
  [[ "$(az resource show --ids "$1" -o json 2>/dev/null |
        jq -r '.tags.ManagedBy // .properties.metadata.ManagedBy // empty')" == SovereignShield ]]
}

group_tagged() {
  [[ "$(az group show --name "$1" -o json 2>/dev/null | jq -r '.tags.ManagedBy // empty')" == SovereignShield ]]
}

# Succeeds only when the CLI positively reports the object missing; any other error counts as present.
gone() {
  local error
  error="$("$@" 2>&1 >/dev/null)" && return 1
  grep -qiE 'not[ _]?found|not be found|does not exist|RESOURCE_DOES_NOT_EXIST' <<<"$error"
}

show() {
  case "$1" in
    view|table) databricks tables get "$2" -o json ;;
    function) databricks functions get "$2" -o json ;;
    volume) databricks volumes read "$2" -o json ;;
    schema) databricks schemas get "$2" -o json ;;
    catalog) databricks catalogs get "$2" -o json ;;
    external_location) databricks external-locations get "$2" -o json ;;
    storage_credential) databricks storage-credentials get "$2" -o json ;;
    sql_warehouse) databricks warehouses get "$3" -o json ;;
    role_assignment) az rest --method get --url "$3?api-version=2022-04-01" ;;
    resource_group) az group show --name "$2" -o json ;;
    *) az resource show --ids "$3" -o json ;;
  esac
}

# A deleted SQL warehouse can still answer, with state DELETED.
absent() {
  local json
  if [[ "$1" == sql_warehouse ]] && json="$(databricks warehouses get "$3" -o json 2>/dev/null)"; then
    [[ "$(jq -r '.state // empty' <<<"$json")" == DELETED ]]
    return
  fi
  gone show "$@"
}

# A created Azure resource is still ours while it is confirmed gone or still carries our marker.
ours() {
  case "$1" in
    resource_group) absent "$@" || group_tagged "$2" ;;
    access_connector|databricks_workspace|storage_container|storage_account|key_vault)
      absent "$@" || still_tagged "$3" ;;
  esac
}

# Succeeds only once the object is reported missing, whether before or after its delete.
remove() {
  local kind="$1" name="$2" id="$3" attempt
  absent "$kind" "$name" "$id" && return 0
  case "$kind" in
    view|table) databricks tables delete "$name" ;;
    function) databricks functions delete "$name" ;;
    volume) databricks volumes delete "$name" ;;
    schema) databricks schemas delete "$name" ;;
    catalog)
      # Unity Catalog creates an empty default schema with every catalog; a non-empty one blocks the drop.
      gone databricks schemas get "$name.default" -o json || databricks schemas delete "$name.default" || return 1
      databricks catalogs delete "$name" ;;
    external_location) databricks external-locations delete "$name" ;;
    storage_credential) databricks storage-credentials delete "$name" ;;
    sql_warehouse) databricks warehouses delete "$id" ;;
    role_assignment) az role assignment delete --ids "$id" ;;
    access_connector|databricks_workspace|storage_container|storage_account|key_vault)
      still_tagged "$id" || { note "kept $kind $name: ManagedBy is no longer SovereignShield"; return 1; }
      az resource delete --ids "$id" ;;
    resource_group)
      group_tagged "$name" || { note "kept resource group $name: ManagedBy tag no longer SovereignShield"; return 1; }
      [[ "$(az resource list --resource-group "$name" -o json | jq length)" == 0 ]] ||
        { note "kept resource group $name: it still contains resources"; return 1; }
      az group delete --name "$name" --yes ;;
    *)
      note "kept $kind $name: unknown kind"; return 1 ;;
  esac || return 1
  for attempt in 1 2 3 4 5 6; do
    absent "$kind" "$name" "$id" && return 0
    if ((attempt < 6)); then sleep "${SOVEREIGN_RETRY_SECONDS:-10}"; fi
  done
  note "kept $kind $name: still reported present after its delete"
  return 1
}

# An adopted parent keeps whatever was built on it, so ownership is settled before any deletion.
ADOPTED=()
while read -r entry; do
  kind="$(jq -r .kind <<<"$entry")" name="$(jq -r .name <<<"$entry")" id="$(jq -r .id <<<"$entry")"
  ours "$kind" "$name" "$id" </dev/null || ADOPTED+=("$kind $name")
done <<<"$plan"
if ((${#ADOPTED[@]})); then
  printf '\nNothing was deleted. These no longer carry ManagedBy=SovereignShield, or it could not be read:\n' >&2
  printf '  %s\n' "${ADOPTED[@]}" >&2
  printf 'Teardown cannot tell what a new owner relies on. Restore the marker and rerun, or keep the estate:\n' >&2
  printf 'remove what you no longer need by hand and archive %s.\n' "$MANIFEST" >&2
  exit 2
fi

((PLAN_ONLY)) && { note "Dry run: nothing was changed."; exit 0; }
if ((!ASSUME_YES)); then
  [[ -t 0 ]] || die "Refusing to delete without confirmation; rerun in a terminal or with --yes."
  read -r -p "Type DELETE to remove the $(grep -c . <<<"$plan") resources marked DELETE: " answer
  [[ "$answer" == DELETE ]] || die "Teardown cancelled; nothing was changed."
fi

while read -r entry; do
  kind="$(jq -r .kind <<<"$entry")" name="$(jq -r .name <<<"$entry")" id="$(jq -r .id <<<"$entry")"
  note "delete  $kind $name"
  if ! remove "$kind" "$name" "$id" </dev/null; then
    printf '\nTeardown stopped at %s %s; it and the rest of the plan stay in the manifest. Resolve the cause and rerun.\n' \
      "$kind" "$name" >&2
    exit 2
  fi
  mark_deleted "$kind" "$name"
done <<<"$plan"
note "Teardown complete. Key Vaults remain soft-deleted under their retention policy; none were purged."
