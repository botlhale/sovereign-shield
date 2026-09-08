# Root composition.
#
# Ordering is a security property, not a convenience: identity exists before the
# workspace, the workspace before the catalog, and the catalog before anything
# that can read from it. No table is ever reachable before the groups that
# constrain it exist.

# The resource group is either created here or adopted.
#
# Adoption is not a workaround. In a regulated estate the resource group is
# routinely provisioned by a platform team through a landing zone, and the
# workload identity is deliberately denied Microsoft.Resources/subscriptions/
# resourceGroups/write. Insisting on creating it would make the configuration
# unusable exactly where this architecture is meant to run. It is also the
# correct setting after the sh/ quickstart, which creates the group before
# Terraform ever sees it.
resource "azurerm_resource_group" "main" {
  count = var.create_resource_group ? 1 : 0

  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

data "azurerm_resource_group" "existing" {
  count = var.create_resource_group ? 0 : 1

  name = var.resource_group_name
}

locals {
  resource_group_name = var.create_resource_group ? azurerm_resource_group.main[0].name : data.azurerm_resource_group.existing[0].name

  # Location follows the group when adopting. A resource placed in a different
  # region from its own resource group is legal in Azure and almost always a
  # mistake, so var.location is ignored rather than trusted here.
  location = var.create_resource_group ? azurerm_resource_group.main[0].location : data.azurerm_resource_group.existing[0].location
}

module "identity" {
  source = "./modules/identity"

  resource_group_name = local.resource_group_name
  location            = local.location
  tenant_id           = var.tenant_id

  group_prefix            = var.group_prefix
  reporting_jurisdictions = var.reporting_jurisdictions
  github_repository       = var.github_repository
  github_environment      = var.github_environment

  tags = var.tags
}

module "databricks_workspace" {
  source = "./modules/databricks_workspace"

  resource_group_name = local.resource_group_name
  location            = local.location
  workspace_name      = var.workspace_name

  key_vault_id  = module.identity.key_vault_id
  key_vault_uri = module.identity.key_vault_uri

  worker_count_min        = var.worker_count_min
  worker_count_max        = var.worker_count_max
  node_type_id            = var.node_type_id
  enable_photon           = var.enable_photon
  autotermination_minutes = var.autotermination_minutes

  tags = var.tags
}

module "unity_catalog_governance" {
  source = "./modules/unity_catalog_governance"

  catalog_name        = var.catalog_name
  schema_name         = var.schema_name
  storage_root        = module.databricks_workspace.external_location_url
  admin_group         = module.identity.group_names["admin"]
  persona_group_names = module.identity.group_names
  grant_tables        = var.grant_tables

  account_groups_ready = var.account_groups_ready

  sql_warehouse_size              = var.sql_warehouse_size
  sql_warehouse_auto_stop_minutes = var.sql_warehouse_auto_stop_minutes
  sql_warehouse_max_clusters      = var.sql_warehouse_max_clusters

  depends_on = [module.databricks_workspace]
}

module "dissemination_gateway" {
  source = "./modules/dissemination_gateway"
  count  = var.deploy_dissemination_gateway ? 1 : 0

  resource_group_name = local.resource_group_name
  location            = local.location

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
