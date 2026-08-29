output "workspace_id" {
  description = "Azure resource id, used to configure the Databricks provider."
  value       = azurerm_databricks_workspace.main.id
}

output "workspace_host" {
  description = "Workspace hostname without a scheme, as the SQL connector expects."
  value       = azurerm_databricks_workspace.main.workspace_url
}

output "workspace_numeric_id" {
  description = "Numeric workspace id, needed for account-level workspace assignment."
  value       = azurerm_databricks_workspace.main.workspace_id
}

output "metastore_id" {
  description = "Metastore the workspace is attached to."
  value       = azurerm_databricks_workspace.main.id
}

output "external_location_url" {
  description = "abfss:// root for the managed schema."
  value       = databricks_external_location.main.url
}

output "storage_credential_name" {
  description = "Managed-identity storage credential name."
  value       = databricks_storage_credential.main.name
}

output "secret_scope_name" {
  description = "Key Vault-backed secret scope."
  value       = databricks_secret_scope.key_vault.name
}
