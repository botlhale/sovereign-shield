#!/usr/bin/env bash
# =====================================================================
# Surgical teardown for scripts/sovereign_up_custom.sh.
#
# Reads the provisioning manifest and removes only the resources it records as
# created by Sovereign Shield, in reverse dependency order. Attached, pre-existing
# resources (resource groups, workspaces, metastores, shared vaults or storage) are
# never touched. Azure resources must still carry ManagedBy=SovereignShield; a
# changed or missing tag means someone else now depends on it, so it is kept.
# Schemas and catalogs are dropped without force: anything added since stays.
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
((PLAN_ONLY)) && { note "Dry run: nothing was changed."; exit 0; }
if ((!ASSUME_YES)); then
  [[ -t 0 ]] || die "Refusing to delete without confirmation; rerun in a terminal or with --yes."
  read -r -p "Type DELETE to remove the $(grep -c . <<<"$plan") resources marked DELETE: " answer
  [[ "$answer" == DELETE ]] || die "Teardown cancelled; nothing was changed."
fi

mark_deleted() {
  local temporary
  temporary="$(mktemp "${MANIFEST}.XXXXXX")"
  jq --arg kind "$1" --arg name "$2" --arg now "$(now)" '
    .updated_at = $now
    | .resources |= map(if .kind == $kind and .name == $name and .deleted_at == null then .deleted_at = $now else . end)' \
    "$MANIFEST" >"$temporary" && mv "$temporary" "$MANIFEST"
}

still_tagged() {
  [[ "$(az resource show --ids "$1" -o json 2>/dev/null | jq -r '.tags.ManagedBy // empty')" == SovereignShield ]]
}

KEPT=()
remove() {
  local kind="$1" name="$2" id="$3"
  case "$kind" in
    view|table)
      databricks tables get "$name" -o json >/dev/null 2>&1 || return 0
      databricks tables delete "$name" ;;
    function)
      databricks functions get "$name" -o json >/dev/null 2>&1 || return 0
      databricks functions delete "$name" ;;
    volume)
      databricks volumes read "$name" -o json >/dev/null 2>&1 || return 0
      databricks volumes delete "$name" ;;
    schema)
      databricks schemas get "$name" -o json >/dev/null 2>&1 || return 0
      databricks schemas delete "$name" ;;
    catalog)
      databricks catalogs get "$name" -o json >/dev/null 2>&1 || return 0
      # Unity Catalog creates an empty default schema with every catalog; a non-empty one blocks the drop.
      if databricks schemas get "$name.default" -o json >/dev/null 2>&1; then
        databricks schemas delete "$name.default" || return 1
      fi
      databricks catalogs delete "$name" ;;
    external_location)
      databricks external-locations get "$name" -o json >/dev/null 2>&1 || return 0
      databricks external-locations delete "$name" ;;
    storage_credential)
      databricks storage-credentials get "$name" -o json >/dev/null 2>&1 || return 0
      databricks storage-credentials delete "$name" ;;
    sql_warehouse)
      databricks warehouses get "$id" -o json >/dev/null 2>&1 || return 0
      databricks warehouses delete "$id" ;;
    role_assignment)
      # Deleting an absent assignment by ID succeeds, so no lookup is needed.
      az role assignment delete --ids "$id" ;;
    storage_container)
      az resource show --ids "$id" -o json >/dev/null 2>&1 || return 0
      az resource delete --ids "$id" ;;
    access_connector|databricks_workspace|storage_account|key_vault)
      az resource show --ids "$id" -o json >/dev/null 2>&1 || return 0
      still_tagged "$id" || { note "kept $kind $name: ManagedBy tag no longer SovereignShield"; return 1; }
      az resource delete --ids "$id" ;;
    resource_group)
      az group show --name "$name" -o json >/dev/null 2>&1 || return 0
      [[ "$(az group show --name "$name" -o json | jq -r '.tags.ManagedBy // empty')" == SovereignShield ]] ||
        { note "kept resource group $name: ManagedBy tag no longer SovereignShield"; return 1; }
      [[ "$(az resource list --resource-group "$name" -o json | jq length)" == 0 ]] ||
        { note "kept resource group $name: it still contains resources"; return 1; }
      az group delete --name "$name" --yes ;;
    *)
      note "kept $kind $name: unknown kind"; return 1 ;;
  esac
}

while read -r entry; do
  kind="$(jq -r .kind <<<"$entry")" name="$(jq -r .name <<<"$entry")" id="$(jq -r .id <<<"$entry")"
  note "delete  $kind $name"
  if remove "$kind" "$name" "$id" </dev/null; then
    mark_deleted "$kind" "$name"
  else
    KEPT+=("$kind $name")
  fi
done <<<"$plan"

if ((${#KEPT[@]})); then
  printf '\nKept (review manually):\n' >&2
  printf '  %s\n' "${KEPT[@]}" >&2
  exit 2
fi
note "Teardown complete. Key Vaults remain soft-deleted under their retention policy; none were purged."
