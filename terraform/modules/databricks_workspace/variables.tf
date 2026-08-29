variable "resource_group_name" {
  description = "Resource group for the workspace and its storage."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "workspace_name" {
  description = "Azure Databricks workspace name."
  type        = string
}

variable "key_vault_id" {
  description = "Key Vault backing the Databricks secret scope."
  type        = string
}

variable "key_vault_uri" {
  description = "Key Vault DNS URI."
  type        = string
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
