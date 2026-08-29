# Unity Catalog access-control plane.
#
# OWNERSHIP BOUNDARY - read before adding anything here.
#
# This module owns the catalog, the schema, the SQL warehouse, and the broad
# RBAC grants. It does NOT own:
#
#   * table DDL
#   * the policy UDFs (fn_rls_lbs_multi_persona_lock, fn_ddm_obs_conf_mask)
#   * the SET ROW FILTER / SET MASK bindings
#
# Those live in src/unity_catalog_triple_lock.sql and are applied by Databricks
# Asset Bundles. Unity Catalog refuses to replace a function that is bound to a
# live filter, so the pipeline detaches, replaces and re-attaches on every run.
# A Terraform resource describing the same binding would report drift after
# every pipeline execution, and an apply could detach a live filter mid-query.
#
# Grants use `databricks_grant` (singular), which is ADDITIVE. The plural
# `databricks_grants` is authoritative and revokes any privilege it does not
# declare - which would silently strip whatever the SQL quickstart path granted.
# The two paths therefore converge instead of fighting.

locals {
  full_schema = "${var.catalog_name}.${var.schema_name}"

  # Everyone reaches the catalog and schema. Traversal reveals nothing on its
  # own; the row filter decides what a query returns.
  traversal_groups = values(var.persona_group_names)

  history_table = "${local.full_schema}.lbs_sdmx_history"
  micro_table   = "${local.full_schema}.lbs_micro_transactions"

  # Institution-identifying detail. Submitters only - protecting the aggregate
  # while leaving the source open is not sovereignty.
  micro_reader_groups = [
    for key, name in var.persona_group_names : name
    if startswith(key, "submitter-")
  ]
}

# ---------------------------------------------------------------------------
# Catalog and schema
# ---------------------------------------------------------------------------

resource "databricks_catalog" "main" {
  name         = var.catalog_name
  metastore_id = var.metastore_id
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
  for_each = toset(local.traversal_groups)

  schema     = "${databricks_catalog.main.name}.${databricks_schema.main.name}"
  principal  = each.value
  privileges = ["USE_SCHEMA"]
}

resource "databricks_grant" "admin_schema_ownership" {
  schema    = "${databricks_catalog.main.name}.${databricks_schema.main.name}"
  principal = var.admin_group
  privileges = [
    "ALL_PRIVILEGES",
    "CREATE_TABLE",
    "CREATE_FUNCTION",
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
  max_num_clusters          = 1

  tags {
    custom_tags {
      key   = "project"
      value = "sovereignshield"
    }
  }
}

resource "databricks_permissions" "warehouse_usage" {
  sql_endpoint_id = databricks_sql_endpoint.dissemination.id

  dynamic "access_control" {
    for_each = toset(local.traversal_groups)
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}
