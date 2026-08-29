# Provider configuration.
#
# No credential is declared here. Authentication comes from ambient context:
#   * In CI - an OIDC token exchanged for an Entra ID access token by the
#     azure/login action. ARM_USE_OIDC=true, and no client secret exists.
#   * Locally - the operator's `az login` session.
#
# There is deliberately no `client_secret` argument and no variable that could
# supply one. See tests/test_secret_decoupling.py, which fails the build if a
# secret-shaped Terraform variable is ever declared.

provider "azurerm" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id

  features {
    key_vault {
      # Soft-delete recovery is on by default; purge stays manual so a destroy
      # cannot silently discard secrets that other environments still reference.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}

provider "azuread" {
  tenant_id = var.tenant_id
}

# Workspace-scoped Databricks provider. The workspace is created in the same
# apply, so the resource id is taken from the module output rather than a
# hardcoded URL.
provider "databricks" {
  azure_workspace_resource_id = module.databricks_workspace.workspace_id
}
