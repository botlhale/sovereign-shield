# Unity Catalog access-control plane.
#
# OWNERSHIP BOUNDARY - read before adding anything here.
#
# This module owns the catalog, the schema, the SQL warehouse, and the broad
# RBAC grants. It does NOT own:
#
#   * table DDL
#   * the policy UDFs (fn_rls_multi_persona_lock, fn_ddm_obs_conf_mask)
#   * the SET ROW FILTER / SET MASK bindings
#
# Those live in src/unity_catalog_triple_lock.sql and are applied by Databricks
# Asset Bundles. Unity Catalog refuses to replace a function that is bound to a
# live filter, so the pipeline detaches, replaces and re-attaches on every run.
# A Terraform resource describing the same binding would report drift after
# every pipeline execution, and an apply could detach a live filter mid-query.
#
# Grants use `databricks_grant` (singular), which is authoritative for one
# (securable, principal) PAIR and leaves other principals on that securable
# alone. The plural `databricks_grants` is authoritative for the whole securable
# and would revoke anything it does not declare, including whatever the SQL
# quickstart path granted. The two paths therefore converge instead of fighting.
#
# The corollary is that no two resources here may target the same pair. Both
# would write, then read back the union and reject it as not matching their own
# list - see the admin exclusion in schema_traversal below.

locals {
  full_schema = "${var.catalog_name}.${var.schema_name}"

  # Everyone reaches the catalog and schema. Traversal reveals nothing on its
  # own; the row filter decides what a query returns.
  #
  # Empty until the groups exist in the Databricks account directory. Databricks
  # resolves principals there, not in Entra ID, so granting earlier fails.
  traversal_groups = var.account_groups_ready ? values(var.persona_group_names) : []

  history_table = "${local.full_schema}.agg_sdmx_history"
  micro_table   = "${local.full_schema}.lbs_micro_transactions"

  # Institution-identifying detail. Submitters only - protecting the aggregate
  # while leaving the source open is not sovereignty.
  micro_reader_groups = var.account_groups_ready ? [
    for key, name in var.persona_group_names : name
    if startswith(key, "submitter-")
  ] : []
}

# ---------------------------------------------------------------------------
# Catalog and schema
# ---------------------------------------------------------------------------

# metastore_id is deliberately unset. A workspace is bound to exactly one
# metastore, and the provider resolves it from the workspace it is configured
# against. Passing anything else - including the workspace's own Azure resource
# id, which is a different identifier entirely - is rejected outright.
resource "databricks_catalog" "main" {
  name         = var.catalog_name
  storage_root = var.storage_root
  comment      = "SovereignShield governed BIS LBS submissions (synthetic data)."

  # An accidental destroy would take the entire SCD2 lineage with it.
  force_destroy = false
}

resource "databricks_schema" "main" {
  catalog_name  = databricks_catalog.main.name
  name          = var.schema_name
  comment       = "Macro history, micro ledger, and the published view."
  force_destroy = false
}

resource "databricks_grant" "catalog_traversal" {
  for_each = toset(local.traversal_groups)

  catalog    = databricks_catalog.main.name
  principal  = each.value
  privileges = ["USE_CATALOG"]
}

resource "databricks_grant" "schema_traversal" {
  # Admin is excluded because admin_schema_ownership below already owns this pair.
  # Two databricks_grant resources on one (securable, principal) each write and
  # then read back the union, and each rejects it for not matching its own list.
  for_each = toset([
    for name in local.traversal_groups : name if name != var.admin_group
  ])

  schema     = "${databricks_catalog.main.name}.${databricks_schema.main.name}"
  principal  = each.value
  privileges = ["USE_SCHEMA"]
}

resource "databricks_grant" "admin_schema_ownership" {
  count = var.account_groups_ready ? 1 : 0

  schema    = "${databricks_catalog.main.name}.${databricks_schema.main.name}"
  principal = var.admin_group

  # USE_SCHEMA is implied by ALL_PRIVILEGES but is listed because this resource is
  # the sole authority for the pair, and the API reports it back.
  privileges = [
    "ALL_PRIVILEGES",
    "CREATE_TABLE",
    "CREATE_FUNCTION",
    "USE_SCHEMA",
  ]
}

# ---------------------------------------------------------------------------
# SQL warehouse
# ---------------------------------------------------------------------------

# Serverless, because the dissemination gateway's traffic is bursty and a
# classic warehouse would bill through idle periods. The warehouse grants no
# entitlement of its own - it is the engine the row filter is evaluated in.
resource "databricks_sql_endpoint" "dissemination" {
  name                      = "wh-sovereignshield"
  cluster_size              = var.sql_warehouse_size
  auto_stop_mins            = var.sql_warehouse_auto_stop_minutes
  enable_serverless_compute = true

  # Concurrency and scan cost are separate levers. Size handles a heavy single
  # query; extra clusters handle many simultaneous readers. A public
  # dissemination tier usually needs the second one first.
  max_num_clusters = var.sql_warehouse_max_clusters

  tags {
    custom_tags {
      key   = "project"
      value = "sovereignshield"
    }
  }
}

resource "databricks_permissions" "warehouse_usage" {
  count = var.account_groups_ready ? 1 : 0

  sql_endpoint_id = databricks_sql_endpoint.dissemination.id

  dynamic "access_control" {
    for_each = toset(local.traversal_groups)
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}
