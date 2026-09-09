variable "catalog_name" {
  description = "Unity Catalog catalog name."
  type        = string
}

variable "schema_name" {
  description = "Schema holding the governed tables."
  type        = string
}

variable "intake_schema_name" {
  description = <<-EOT
    Schema holding the domestic micro ledger. Separate from schema_name because the
    ledger is pre-submission material that does not leave the reporting country,
    and because submitters need USE_SCHEMA here to reach their own rows.
  EOT
  type        = string
  default     = "sovereign_intake"
}

variable "submissions_schema_name" {
  description = <<-EOT
    Schema holding the submissions volume. Separate from intake_schema_name because
    submitters traverse intake, and a volume cannot be row-filtered: one holding
    every jurisdiction's filings must stay behind a gate no submitter can open.
  EOT
  type        = string
  default     = "sovereign_submissions"
}

variable "storage_root" {
  description = "abfss:// managed storage root for the catalog."
  type        = string
}

variable "account_groups_ready" {
  description = <<-EOT
    Whether the persona groups have been mirrored into the Databricks *account*.

    Terraform creates them in Entra ID, but Databricks resolves principals
    against its own account directory, which sh/databricks_account_setup.ps1
    populates in Stage 2. Granting before that fails with
    "Principal: GroupName(...) does not exist".

    Leave false for the first apply; set true and re-apply after Stage 2.
  EOT
  type        = bool
  default     = false
}

variable "admin_group" {
  description = "Group holding the administrator / central auditor persona."
  type        = string
}

variable "persona_group_names" {
  description = "Persona key -> Entra ID group display name."
  type        = map(string)
}

variable "sql_warehouse_size" {
  description = "Serverless warehouse size."
  type        = string
  default     = "2X-Small"
}

variable "sql_warehouse_auto_stop_minutes" {
  description = "Idle minutes before the warehouse stops."
  type        = number
  default     = 10
}

variable "sql_warehouse_max_clusters" {
  description = "Upper bound for warehouse multi-cluster load balancing."
  type        = number
  default     = 1
}

variable "grant_tables" {
  description = <<-EOT
    Apply table-level grants. Leave false until the Asset Bundle has created the
    tables; a grant on a non-existent securable fails the apply.
  EOT
  type        = bool
  default     = false
}
