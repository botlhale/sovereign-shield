# Everything a follow-on step needs, and nothing that would be a disclosure.
# No credential is emitted: the proxy password exists only in Key Vault.

output "key_vault_name" {
  description = "Vault name. sh/pre_auth.ps1 discovers this by prefix rather than hardcoding it."
  value       = module.identity.key_vault_name
}

output "workspace_url" {
  description = "Databricks workspace URL."
  value       = "https://${module.databricks_workspace.workspace_host}"
}

output "workspace_numeric_id" {
  description = "Numeric workspace id, for account-level workspace assignment."
  value       = module.databricks_workspace.workspace_numeric_id
}

output "sql_warehouse_id" {
  description = "Pass to the bundle: databricks bundle deploy --var=\"warehouse_id=...\""
  value       = module.unity_catalog_governance.sql_warehouse_id
}

output "persona_groups" {
  description = "Entra ID groups the Unity Catalog policy functions resolve."
  value       = module.identity.group_names
}

output "cicd_client_id" {
  description = "Set as the AZURE_CLIENT_ID repository variable for OIDC login."
  value       = module.identity.cicd_client_id
}

output "public_proxy_client_id" {
  description = "Anonymous dissemination identity. Must be added to the Databricks account and the public group."
  value       = module.identity.public_proxy_client_id
}

output "dissemination_gateway_url" {
  description = "Public portal URL, when the Container Apps deployment is enabled."
  value       = try(module.dissemination_gateway[0].portal_url, null)
}

output "next_steps" {
  description = "Ordering that Terraform cannot express, because it spans two systems."
  value       = <<-EOT
    1. Add both service principals to the Databricks ACCOUNT and mirror the
       persona groups there. is_account_group_member() resolves ACCOUNT groups
       only; workspace-scoped groups of the same name silently match nothing.
         ./sh/databricks_account_setup.ps1 -AccountId <account-id>

    2. Deploy the data and policy plane. Terraform does not own table DDL, the
       policy UDFs, or the row filter and mask bindings.
         databricks bundle deploy -t dev --var="warehouse_id=${module.unity_catalog_governance.sql_warehouse_id}"
         databricks bundle run sovereignshield_sdmx_pipeline -t dev

    3. Re-apply with -var="grant_tables=true" so table-level grants can bind to
       tables that now exist.

    4. Verify the anonymous tier is genuinely fail-closed. Every observation
       returned must carry BATCH_STATUS=PUBLISHED and OBS_CONF=F.
  EOT
}
