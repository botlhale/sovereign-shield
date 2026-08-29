variable "resource_group_name" {
  description = "Resource group hosting the Key Vault."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "tenant_id" {
  description = "Entra ID tenant."
  type        = string
}

variable "group_prefix" {
  description = "Prefix for the persona groups; must match the SQL policy functions."
  type        = string
}

variable "reporting_jurisdictions" {
  description = "ISO alpha-2 codes that get a national submitter group."
  type        = list(string)
}

variable "github_repository" {
  description = "owner/repo permitted to assume the deployment identity."
  type        = string
}

variable "github_environment" {
  description = "GitHub environment the federated credential is scoped to."
  type        = string
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
