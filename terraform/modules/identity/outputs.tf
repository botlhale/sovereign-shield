# Outputs carry identifiers only. The public proxy's password is deliberately
# absent: it is written to Key Vault and read from there by whatever needs it,
# so it never crosses a module boundary as a value.

output "group_names" {
  description = "Persona key -> Entra ID group display name."
  value       = { for key, group in azuread_group.persona : key => group.display_name }
}

output "group_object_ids" {
  description = "Persona key -> Entra ID group object id."
  value       = { for key, group in azuread_group.persona : key => group.object_id }
}

output "cicd_client_id" {
  description = "Application (client) id of the deployment identity, for AZURE_CLIENT_ID in GitHub Actions."
  value       = azuread_application.cicd.client_id
}

output "cicd_object_id" {
  description = "Service principal object id of the deployment identity."
  value       = azuread_service_principal.cicd.object_id
}

output "public_proxy_client_id" {
  description = "Application (client) id of the anonymous dissemination proxy."
  value       = azuread_application.public_proxy.client_id
}

output "key_vault_id" {
  description = "Key Vault resource id."
  value       = azurerm_key_vault.main.id
}

output "key_vault_uri" {
  description = "Key Vault DNS URI."
  value       = azurerm_key_vault.main.vault_uri
}

output "key_vault_name" {
  description = "Key Vault name. pre_auth.ps1 discovers this by prefix rather than hardcoding it."
  value       = azurerm_key_vault.main.name
}

output "public_spn_client_id_secret_id" {
  description = "Versionless secret id for the proxy client id, for Container Apps keyvaultref."
  value       = azurerm_key_vault_secret.public_spn_client_id.versionless_id
}

output "public_spn_client_secret_id" {
  description = "Versionless secret id for the proxy secret. Versionless so rotation does not require a redeploy."
  value       = azurerm_key_vault_secret.public_spn_client_secret.versionless_id
}
