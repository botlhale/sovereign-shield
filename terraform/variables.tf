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

variable "create_resource_group" {
  description = <<-EOT
    Create the resource group, or adopt one that already exists.

    Set to false when the group is provisioned outside this configuration. That
    is the normal arrangement in a regulated estate, where a landing zone owns
    resource groups and the workload identity is denied
    Microsoft.Resources/subscriptions/resourceGroups/write. It is also the
    correct setting after the sh/ quickstart, which creates the group first.

    When false, var.location is ignored and the group's own region is used, and
    `terraform destroy` leaves the group in place.
  EOT
  type        = bool
  default     = true
}

variable "location" {
  description = "Azure region. Data residency for a sovereignty demonstrator is not incidental."
  type        = string
  default     = "canadacentral"
}

variable "workspace_name" {
  description = <<-EOT
    Azure Databricks workspace name. Deliberately not the catalog name with hyphens:
    Databricks auto-provisions a default catalog named after the workspace with
    hyphens converted to underscores, and it wins the name whenever it gets there
    first. See the validation on catalog_name.
  EOT
  type        = string
  default     = "dbw-sovshield"
}

variable "catalog_name" {
  description = "Unity Catalog catalog. Must match the literal in unity_catalog_triple_lock.sql."
  type        = string
  default     = "dbw_sovereignshield"

  # Caught here because the runtime symptom is a race, not a constant failure: if
  # the name is free when the workspace is created the platform takes it and apply
  # fails, but if something already holds it the platform appends the org id and
  # the two coexist unnoticed. The same configuration can deploy once and fail on
  # rebuild, so the check has to be on the names rather than on the outcome.
  validation {
    condition     = var.catalog_name != replace(var.workspace_name, "-", "_")
    error_message = "catalog_name collides with the default catalog Databricks creates for workspace_name (hyphens become underscores). Pick a catalog_name that is not derived from the workspace name."
  }
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
    sufficient on its own: fn_rls_multi_persona_lock needs a matching branch
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
  description = <<-EOT
    Serverless SQL warehouse size backing the dissemination gateway. 2X-Small
    serves the evaluation sandbox; Medium through 2X-Large is the range an
    international hub uses for concurrent public researchers.
  EOT
  type        = string
  default     = "2X-Small"
}

variable "sql_warehouse_auto_stop_minutes" {
  description = "Idle minutes before the warehouse stops. The gateway tolerates a cold start."
  type        = number
  default     = 10
}

variable "sql_warehouse_max_clusters" {
  description = <<-EOT
    Upper bound for warehouse multi-cluster load balancing. Raising this adds
    query throughput for concurrent readers without changing warehouse size,
    which is the correct lever when the bottleneck is concurrency rather than
    the cost of any single scan.
  EOT
  type        = number
  default     = 1

  validation {
    condition     = var.sql_warehouse_max_clusters >= 1 && var.sql_warehouse_max_clusters <= 30
    error_message = "sql_warehouse_max_clusters must be between 1 and 30."
  }
}

variable "worker_count_min" {
  description = "Lower bound of the ingestion autoscaling fleet. 0 with worker_count_max = 0 keeps the sandbox single-node."
  type        = number
  default     = 0
}

variable "worker_count_max" {
  description = "Upper bound of the ingestion autoscaling fleet. 0 selects single-node compute."
  type        = number
  default     = 0
}

variable "node_type_id" {
  description = "Azure VM family for ingestion driver and workers."
  type        = string
  default     = "Standard_DS3_v2"
}

variable "enable_photon" {
  description = "Run the vectorised Photon engine on the ingestion cluster policy."
  type        = bool
  default     = false
}

variable "autotermination_minutes" {
  description = "Idle minutes before an interactive cluster on the ingestion policy self-terminates."
  type        = number
  default     = 20
}

variable "deploy_dissemination_gateway" {
  description = <<-EOT
    Provision the Azure Container Apps deployment of the public gateway.
    Only this path can demonstrate genuinely anonymous access - a Databricks App
    always sits behind workspace SSO.

    Off by default because it needs a container image that does not exist until
    Stage 7 builds and pushes one. Enabling it earlier fails after a multi-minute
    rollout with a DNS error against a registry that was never created.
  EOT
  type        = bool
  default     = false
}

variable "gateway_image" {
  description = "Fully qualified container image for the dissemination gateway, e.g. myacr.azurecr.io/sovereignshield-portal:latest"
  type        = string
  default     = ""

  # Fail at plan time rather than after a multi-minute rollout that ends in a
  # DNS lookup against a registry nobody created.
  validation {
    condition     = !var.deploy_dissemination_gateway || trimspace(var.gateway_image) != ""
    error_message = "deploy_dissemination_gateway = true requires gateway_image. Build and push the image first - see Stage 7."
  }
}

variable "account_groups_ready" {
  description = <<-EOT
    Whether the persona groups exist in the Databricks *account* directory.

    Terraform creates them in Entra ID, but Databricks resolves principals
    against its own account directory, which sh/databricks_account_setup.ps1
    populates in Stage 2. Leave false for the first apply; set true and re-apply
    afterwards to attach catalog, schema and warehouse permissions.
  EOT
  type        = bool
  default     = false
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
