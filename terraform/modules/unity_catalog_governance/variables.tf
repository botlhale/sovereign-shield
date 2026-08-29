variable "catalog_name" {
  description = "Unity Catalog catalog name."
  type        = string
}

variable "schema_name" {
  description = "Schema holding the governed tables."
  type        = string
}

variable "metastore_id" {
  description = "Metastore the catalog is created in."
  type        = string
}

variable "storage_root" {
  description = "abfss:// managed storage root for the catalog."
  type        = string
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

variable "grant_tables" {
  description = <<-EOT
    Apply table-level grants. Leave false until the Asset Bundle has created the
    tables; a grant on a non-existent securable fails the apply.
  EOT
  type        = bool
  default     = false
}
