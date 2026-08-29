# Databricks workspace, Unity Catalog storage plumbing, and the Key Vault-backed
# secret scope.
#
# The access connector is what lets Unity Catalog reach storage without any
# credential existing in the data plane: it is a managed identity Azure trusts,
# so no account key or SAS token is ever created, stored, or rotated.

resource "azurerm_databricks_workspace" "main" {
  name                = var.workspace_name
  resource_group_name = var.resource_group_name
  location            = var.location

  # Premium is a hard requirement, not a preference: row filters and column
  # masks do not exist on the standard SKU.
  sku = "premium"

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Unity Catalog storage
# ---------------------------------------------------------------------------

resource "random_string" "storage_suffix" {
  length  = 8
  special = false
  upper   = false
}

resource "azurerm_storage_account" "unity_catalog" {
  name                = "stsovshield${random_string.storage_suffix.result}"
  resource_group_name = var.resource_group_name
  location            = var.location

  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Hierarchical namespace is required for ADLS Gen2, which Unity Catalog
  # external locations are defined against.
  is_hns_enabled = true

  # No public network path to sovereign data, and no anonymous container.
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false

  tags = var.tags
}

resource "azurerm_storage_container" "metastore" {
  name               = "metastore"
  storage_account_id = azurerm_storage_account.unity_catalog.id
}

resource "azurerm_databricks_access_connector" "main" {
  name                = "dbac-sovereignshield"
  resource_group_name = var.resource_group_name
  location            = var.location

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

resource "azurerm_role_assignment" "connector_storage" {
  scope                = azurerm_storage_account.unity_catalog.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.main.identity[0].principal_id
}

resource "databricks_storage_credential" "main" {
  name = "sc-sovereignshield"

  azure_managed_identity {
    access_connector_id = azurerm_databricks_access_connector.main.id
  }

  comment = "Managed identity credential; no account key exists to leak."

  depends_on = [azurerm_role_assignment.connector_storage]
}

resource "databricks_external_location" "main" {
  name = "el-sovereignshield"
  url = format(
    "abfss://%s@%s.dfs.core.windows.net/",
    azurerm_storage_container.metastore.name,
    azurerm_storage_account.unity_catalog.name,
  )
  credential_name = databricks_storage_credential.main.name
  comment         = "Managed storage for the sovereign_shield schema."
}

# ---------------------------------------------------------------------------
# Secret scope
# ---------------------------------------------------------------------------

# Key Vault-backed rather than Databricks-backed. A Databricks-backed scope
# stores the value in the control plane; this one holds only a pointer, so
# rotating in Key Vault takes effect immediately and no copy exists to go stale.
resource "databricks_secret_scope" "key_vault" {
  name                     = "sovereignshield"
  initial_manage_principal = "users"

  keyvault_metadata {
    resource_id = var.key_vault_id
    dns_name    = var.key_vault_uri
  }
}

# ---------------------------------------------------------------------------
# Workspace URL, published for the session credential loader
# ---------------------------------------------------------------------------

# Written here rather than in the identity module because the URL is only known
# once the workspace exists; sourcing it there would create a cycle. A rebuilt
# workspace gets a new URL, and pre_auth.ps1 reads this secret by name - a stale
# value authenticates against a workspace that no longer exists.
resource "azurerm_key_vault_secret" "workspace_url" {
  name         = "databricks-workspace-url"
  value        = "https://${azurerm_databricks_workspace.main.workspace_url}"
  key_vault_id = var.key_vault_id
}
