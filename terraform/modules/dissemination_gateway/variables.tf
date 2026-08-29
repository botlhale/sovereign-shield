variable "resource_group_name" {
  description = "Resource group for the gateway."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "key_vault_id" {
  description = "Key Vault the gateway identity is granted read access to."
  type        = string
}

variable "public_client_id_secret_id" {
  description = "Versionless Key Vault secret id for the proxy client id."
  type        = string
}

variable "public_client_secret_id" {
  description = "Versionless Key Vault secret id for the proxy credential. Versionless so rotation needs no redeploy."
  type        = string
}

variable "workspace_host" {
  description = "Databricks workspace hostname, no scheme."
  type        = string
}

variable "warehouse_id" {
  description = "SQL warehouse the gateway queries through."
  type        = string
}

variable "catalog_name" {
  description = "Unity Catalog catalog."
  type        = string
}

variable "schema_name" {
  description = "Unity Catalog schema."
  type        = string
}

variable "container_image" {
  description = "Fully qualified image built from the repository Dockerfile."
  type        = string
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
