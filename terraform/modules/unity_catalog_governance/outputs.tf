output "catalog_name" {
  description = "Provisioned catalog."
  value       = databricks_catalog.main.name
}

output "schema_full_name" {
  description = "catalog.schema of the governed namespace."
  value       = "${databricks_catalog.main.name}.${databricks_schema.main.name}"
}

output "sql_warehouse_id" {
  description = "Warehouse id for DATABRICKS_WAREHOUSE_ID and the bundle variable."
  value       = databricks_sql_endpoint.dissemination.id
}

output "sql_warehouse_http_path" {
  description = "HTTP path for the SQL connector."
  value       = databricks_sql_endpoint.dissemination.odbc_params[0].path
}
