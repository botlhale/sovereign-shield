# Provider and version pinning for the SovereignShield control plane.
#
# Terraform owns the INFRASTRUCTURE AND ACCESS-CONTROL PLANE: Entra ID groups
# and service principals, OIDC federation, Key Vault, the workspace, catalogs,
# schemas, storage credentials, external locations, the SQL warehouse, and the
# broad RBAC grants.
#
# It deliberately does NOT own the DATA AND POLICY PLANE - table DDL, the policy
# UDFs, and the SET ROW FILTER / SET MASK bindings. Those belong to
# src/unity_catalog_triple_lock.sql, applied by Databricks Asset Bundles.
#
# The split is not stylistic. Row filters are detached and re-attached on every
# pipeline run so the functions they bind can be replaced; if Terraform also
# owned them it would report drift after every run, and an apply could detach a
# live filter mid-query. One writer per object.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.14"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.1"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.62"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  # Configured at init time so no storage account name is committed:
  #   terraform init -backend-config=backend.hcl
  backend "azurerm" {}
}
