# Public Dissemination Gateway on Azure Container Apps.
#
# This is the only deployment that can demonstrate genuinely anonymous access. A
# Databricks App always sits behind workspace SSO, so its "public" tier is an
# authenticated visitor holding no sovereign entitlement - which proves the
# persona matrix but not the anonymous case a real dissemination portal has to
# survive.
#
# Nothing about the security model changes here; only who can knock. The row
# filter remains the sole arbiter of what is returned, and this container holds
# no entitlement of its own beyond membership of the public persona group.

resource "azurerm_log_analytics_workspace" "gateway" {
  name                = "log-sovereignshield-gateway"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_container_app_environment" "gateway" {
  name                       = "cae-sovereignshield"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.gateway.id
  tags                       = var.tags
}

resource "azurerm_user_assigned_identity" "gateway" {
  name                = "id-sovereignshield-gateway"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

# User-assigned rather than system-assigned specifically so the Key Vault role
# assignment can be created BEFORE the container app. A system-assigned identity
# only exists after the app is created, but the app cannot start until it can
# resolve its keyvaultref secrets - a deadlock on first apply.
resource "azurerm_role_assignment" "gateway_secrets_user" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}

resource "azurerm_container_app" "gateway" {
  name                         = "ca-sovereignshield-portal"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.gateway.id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.gateway.id]
  }

  # Credentials are Key Vault references resolved by the platform at start-up.
  # The value never appears in Terraform state, on a command line, or in an
  # environment variable this configuration can read.
  secret {
    name                = "public-spn-client-id"
    key_vault_secret_id = var.public_client_id_secret_id
    identity            = azurerm_user_assigned_identity.gateway.id
  }

  secret {
    name                = "public-spn-client-secret"
    key_vault_secret_id = var.public_client_secret_id
    identity            = azurerm_user_assigned_identity.gateway.id
  }

  ingress {
    # External and unauthenticated by design - this deployment exists to
    # exercise the anonymous tier end to end.
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    # The gateway is stateless, so scaling out is safe. One minimum replica
    # keeps the first visitor off a cold start.
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "portal"
      image  = var.container_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "DATABRICKS_HOST"
        value = var.workspace_host
      }
      env {
        name  = "DATABRICKS_SERVER_HOSTNAME"
        value = var.workspace_host
      }
      env {
        name  = "DATABRICKS_WAREHOUSE_ID"
        value = var.warehouse_id
      }
      env {
        name        = "DATABRICKS_CLIENT_ID"
        secret_name = "public-spn-client-id"
      }
      env {
        name        = "DATABRICKS_CLIENT_SECRET"
        secret_name = "public-spn-client-secret"
      }
      env {
        name  = "SOVEREIGNSHIELD_CATALOG"
        value = var.catalog_name
      }
      env {
        name  = "SOVEREIGNSHIELD_SCHEMA"
        value = var.schema_name
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/v1/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/v1/health"
      }
    }
  }

  depends_on = [azurerm_role_assignment.gateway_secrets_user]
}
