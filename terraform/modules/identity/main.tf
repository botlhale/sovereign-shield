# Entra ID persona groups, deployment identities, OIDC federation and Key Vault.
#
# The groups created here are the sole input to every Unity Catalog policy
# decision. Their names must match the literals in
# src/unity_catalog_triple_lock.sql exactly - a mismatch does not error, it
# fails closed and returns zero rows to everyone.

data "azuread_client_config" "current" {}

locals {
  # Persona key -> display name. The public tier is a real group rather than the
  # absence of one: the row filter fails closed, so "unauthenticated" cannot be a
  # fall-through case or every anonymous visitor would see nothing.
  base_groups = {
    admin       = "${var.group_prefix}-admin"
    researchers = "${var.group_prefix}-researchers"
    public      = "${var.group_prefix}-public"
  }

  submitter_groups = {
    for code in var.reporting_jurisdictions :
    "submitter-${code}" => "${var.group_prefix}-submitter-${code}"
  }

  all_groups = merge(local.base_groups, local.submitter_groups)
}

# ---------------------------------------------------------------------------
# Persona groups
# ---------------------------------------------------------------------------

resource "azuread_group" "persona" {
  for_each = local.all_groups

  display_name     = each.value
  mail_enabled     = false
  security_enabled = true
  description      = "SovereignShield persona: ${each.key}"

  # Membership is managed outside Terraform. Human persona assignment is an
  # administrative act with its own approval path, and putting it in state would
  # mean a `terraform apply` could silently remove someone's access.
  lifecycle {
    ignore_changes = [members, owners]
  }
}

# ---------------------------------------------------------------------------
# CI/CD deployment identity - OIDC only, no client secret
# ---------------------------------------------------------------------------

resource "azuread_application" "cicd" {
  display_name     = "spn-sovereignshield-cicd"
  owners           = [data.azuread_client_config.current.object_id]
  sign_in_audience = "AzureADMyOrg"
}

resource "azuread_service_principal" "cicd" {
  client_id = azuread_application.cicd.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# Workload identity federation. GitHub Actions presents a short-lived OIDC token
# and receives an Entra access token in exchange, so there is no client secret in
# repository settings to leak, rotate, or forget.
resource "azuread_application_federated_identity_credential" "github_environment" {
  application_id = azuread_application.cicd.id
  display_name   = "github-${var.github_environment}"
  description    = "GitHub Actions OIDC for ${var.github_repository} (${var.github_environment})"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"

  # Scoped to one repository AND one environment. A subject of
  # repo:owner/repo:ref:refs/heads/* would let any branch assume the production
  # identity, which defeats the review gate entirely.
  subject = "repo:${var.github_repository}:environment:${var.github_environment}"
}

resource "azuread_application_federated_identity_credential" "github_pull_request" {
  application_id = azuread_application.cicd.id
  display_name   = "github-pull-request"
  description    = "Plan-only identity for pull requests"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.github_repository}:pull_request"
}

resource "azurerm_role_assignment" "cicd_contributor" {
  scope                = data.azurerm_resource_group.main.id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.cicd.object_id
}

# The SCD2 engine reads the history table to find records to expire. If the row
# filter hid them the merge would treat every row as new and silently duplicate
# history, so the deployment identity must hold the admin persona.
resource "azuread_group_member" "cicd_is_admin" {
  group_object_id  = azuread_group.persona["admin"].object_id
  member_object_id = azuread_service_principal.cicd.object_id
}

# ---------------------------------------------------------------------------
# Public dissemination proxy identity
# ---------------------------------------------------------------------------

# Created with NO Azure RBAC role assignment. `az ad sp create-for-rbac` would
# grant Contributor over the subscription; this principal has no business
# touching the control plane. Its entire entitlement is the Unity Catalog row
# filter attached to the public group: published, free-to-publish rows.
resource "azuread_application" "public_proxy" {
  display_name     = "spn-sovereignshield-public"
  owners           = [data.azuread_client_config.current.object_id]
  sign_in_audience = "AzureADMyOrg"
}

resource "azuread_service_principal" "public_proxy" {
  client_id = azuread_application.public_proxy.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_group_member" "public_proxy_is_public" {
  group_object_id  = azuread_group.persona["public"].object_id
  member_object_id = azuread_service_principal.public_proxy.object_id
}

# The Container Apps deployment authenticates as this principal and cannot use
# OIDC, so it needs a secret. Rotation is automatic and the value never leaves
# Key Vault - the container resolves it through a keyvaultref, so it is not
# passed on a command line or written to a file.
resource "time_rotating" "public_proxy" {
  rotation_days = 90
}

resource "azuread_service_principal_password" "public_proxy" {
  service_principal_id = azuread_service_principal.public_proxy.id
  rotate_when_changed = {
    rotation = time_rotating.public_proxy.id
  }
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------

data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

resource "random_integer" "vault_suffix" {
  min = 10000
  max = 99999
}

resource "azurerm_key_vault" "main" {
  name                = "kv-sovereignshield-${random_integer.vault_suffix.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = var.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 90

  tags = var.tags
}

# The operator running the apply needs write access to seed the secrets.
resource "azurerm_role_assignment" "deployer_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azuread_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "public_spn_client_id" {
  name         = "public-spn-client-id"
  value        = azuread_application.public_proxy.client_id
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]
}

resource "azurerm_key_vault_secret" "public_spn_client_secret" {
  name         = "public-spn-client-secret"
  value        = azuread_service_principal_password.public_proxy.value
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]
}

resource "azurerm_key_vault_secret" "tenant_id" {
  name         = "spn-tenant-id"
  value        = var.tenant_id
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_secrets_officer]
}
