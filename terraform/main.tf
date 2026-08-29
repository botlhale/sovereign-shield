# Root composition.
#
# Ordering is a security property, not a convenience: identity exists before the
# workspace, the workspace before the catalog, and the catalog before anything
# that can read from it. No table is ever reachable before the groups that
# constrain it exist.

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

module "identity" {
  source = "./modules/identity"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = var.tenant_id

  group_prefix            = var.group_prefix
  reporting_jurisdictions = var.reporting_jurisdictions
  github_repository       = var.github_repository
  github_environment      = var.github_environment

  tags = var.tags
}

module "databricks_workspace" {
  source = "./modules/databricks_workspace"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_name      = var.workspace_name

  key_vault_id  = module.identity.key_vault_id
  key_vault_uri = module.identity.key_vault_uri

  tags = var.tags
}

module "unity_catalog_governance" {
  source = "./modules/unity_catalog_governance"

  catalog_name        = var.catalog_name
  schema_name         = var.schema_name
  metastore_id        = module.databricks_workspace.metastore_id
  storage_root        = module.databricks_workspace.external_location_url
  admin_group         = module.identity.group_names["admin"]
  persona_group_names = module.identity.group_names
  grant_tables        = var.grant_tables

  sql_warehouse_size              = var.sql_warehouse_size
  sql_warehouse_auto_stop_minutes = var.sql_warehouse_auto_stop_minutes

  depends_on = [module.databricks_workspace]
}

module "dissemination_gateway" {
  source = "./modules/dissemination_gateway"
  count  = var.deploy_dissemination_gateway ? 1 : 0

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  key_vault_id               = module.identity.key_vault_id
  public_client_id_secret_id = module.identity.public_spn_client_id_secret_id
  public_client_secret_id    = module.identity.public_spn_client_secret_id

  workspace_host  = module.databricks_workspace.workspace_host
  warehouse_id    = module.unity_catalog_governance.sql_warehouse_id
  catalog_name    = var.catalog_name
  schema_name     = var.schema_name
  container_image = var.gateway_image

  tags = var.tags
}
