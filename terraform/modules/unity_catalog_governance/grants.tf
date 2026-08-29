# Table-level grants.
#
# Separated from the catalog/schema file because these depend on tables that
# Databricks Asset Bundles create. On a first apply the tables do not exist yet,
# so these are applied on the second pass:
#
#   terraform apply                      # catalog, schema, warehouse
#   databricks bundle run ...            # tables and policies
#   terraform apply -var=grant_tables=true
#
# Making that ordering explicit is preferable to a Terraform run that fails
# halfway with a confusing "table not found" and leaves the platform partially
# granted.

resource "databricks_grant" "history_readers" {
  for_each = var.grant_tables ? toset(values(var.persona_group_names)) : toset([])

  table     = local.history_table
  principal = each.value

  # Deliberately broad for every persona. The grant decides reachability; the
  # row filter decides visibility. Expressing sovereignty through grants instead
  # would need one securable per jurisdiction and still could not mask a cell.
  privileges = ["SELECT"]
}

resource "databricks_grant" "micro_readers" {
  for_each = var.grant_tables ? toset(local.micro_reader_groups) : toset([])

  table      = local.micro_table
  principal  = each.value
  privileges = ["SELECT"]
}

resource "databricks_grant" "admin_tables" {
  for_each = var.grant_tables ? toset([local.history_table, local.micro_table]) : toset([])

  table      = each.value
  principal  = var.admin_group
  privileges = ["ALL_PRIVILEGES"]
}
