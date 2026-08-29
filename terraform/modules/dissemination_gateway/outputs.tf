output "fqdn" {
  description = "Public hostname of the dissemination gateway."
  value       = azurerm_container_app.gateway.ingress[0].fqdn
}

output "portal_url" {
  description = "Portal entry point."
  value       = "https://${azurerm_container_app.gateway.ingress[0].fqdn}"
}

output "identity_principal_id" {
  description = "Gateway managed identity, for Key Vault auditing."
  value       = azurerm_user_assigned_identity.gateway.principal_id
}
