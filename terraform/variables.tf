# Root inputs.
#
# Every variable here is a location, a name, or a toggle. None of them is a
# credential, and none may become one: secrets are resolved from Key Vault at
# apply time or injected by the platform at run time.

variable "subscription_id" {
  description = "Azure subscription that hosts the platform."
  type        = string
}

variable "tenant_id" {
  description = "Entra ID tenant."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for every SovereignShield resource."
  type        = string
  default     = "rg-sovereignshield"
}

variable "location" {
  description = "Azure region. Data residency for a sovereignty demonstrator is not incidental."
  type        = string
  default     = "canadacentral"
}

variable "workspace_name" {
  description = "Azure Databricks workspace name."
  type        = string
  default     = "dbw-sovereignshield"
}

variable "catalog_name" {
  description = "Unity Catalog catalog. Must match the literal in unity_catalog_triple_lock.sql."
  type        = string
  default     = "dbw_sovereignshield"
}

variable "schema_name" {
  description = "Unity Catalog schema holding the governed tables."
  type        = string
  default     = "sovereign_shield"
}

variable "group_prefix" {
  description = "Prefix for the Entra ID persona groups. Changing it requires the SQL policy functions to change in lockstep."
  type        = string
  default     = "sg-sovereignshield"
}

variable "reporting_jurisdictions" {
  description = <<-EOT
    ISO alpha-2 codes with a national submitter group. Adding one here is not
    sufficient on its own: fn_rls_lbs_multi_persona_lock needs a matching branch
    and the MVSD needs rows for it, or the new group resolves to zero rows.
  EOT
  type        = list(string)
  default     = ["ca", "us"]

  validation {
    condition     = alltrue([for c in var.reporting_jurisdictions : can(regex("^[a-z]{2}$", c))])
    error_message = "Jurisdictions must be lower-case ISO alpha-2 codes."
  }
}

variable "github_repository" {
  description = "owner/repo permitted to assume the deployment identity via OIDC."
  type        = string
  default     = "botnt/sovereign-shield"

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "Expected the form owner/repo."
  }
}

variable "github_environment" {
  description = "GitHub environment the federated credential is scoped to."
  type        = string
  default     = "production"
}

variable "sql_warehouse_size" {
  description = "Serverless SQL warehouse size backing the dissemination gateway."
  type        = string
  default     = "2X-Small"
}

variable "sql_warehouse_auto_stop_minutes" {
  description = "Idle minutes before the warehouse stops. The gateway tolerates a cold start."
  type        = number
  default     = 10
}

variable "deploy_dissemination_gateway" {
  description = <<-EOT
    Provision the Azure Container Apps deployment of the public gateway.
    Only this path can demonstrate genuinely anonymous access - a Databricks App
    always sits behind workspace SSO.
  EOT
  type        = bool
  default     = true
}

variable "gateway_image" {
  description = "Fully qualified container image for the dissemination gateway."
  type        = string
  default     = ""
}

variable "grant_tables" {
  description = <<-EOT
    Apply table-level grants. Leave false on the first apply: the tables are
    created by the Asset Bundle, and a grant on a non-existent securable fails.
    Re-apply with true once the pipeline has run.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project    = "sovereignshield"
    dataset    = "synthetic"
    managed_by = "terraform"
  }
}
