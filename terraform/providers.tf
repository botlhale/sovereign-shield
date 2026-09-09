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

  # The Unity Catalog storage account sets shared_access_key_enabled = false, so
  # there is no account key for the provider to fall back on. Without this the
  # post-create blob-service poll is rejected with
  # "Key based authentication is not permitted on this storage account".
  storage_use_azuread = true

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
#
# The cost of that convenience shows up whenever the workspace is replaced: this
# id is unknown for the duration, so the provider cannot resolve a host and both
# reads and destroys of databricks_* resources fail with "cannot configure default
# credentials" - an auth error whose real cause is an unknown target. Setting
# DATABRICKS_HOST for that one run configures the provider from the environment
# instead. See the troubleshooting section of steps_terraform.md.
provider "databricks" {
  azure_workspace_resource_id = module.databricks_workspace.workspace_id
}
