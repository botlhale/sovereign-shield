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

variable "worker_count_min" {
  description = <<-EOT
    Lower bound of the autoscaling worker fleet for the ingestion and SCD2 merge
    workload. Leave at 0 together with worker_count_max to keep the evaluation
    sandbox on driver-only compute.
  EOT
  type        = number
  default     = 0
}

variable "worker_count_max" {
  description = <<-EOT
    Upper bound of the autoscaling worker fleet. 0 selects single-node compute.
    An international hub ingesting every member jurisdiction sets this to the
    number of country partitions it wants merged in parallel; 8-16 is typical.
  EOT
  type        = number
  default     = 0

  validation {
    condition     = var.worker_count_max == 0 || var.worker_count_max >= var.worker_count_min
    error_message = "worker_count_max must be 0 (single node) or >= worker_count_min."
  }
}

variable "node_type_id" {
  description = <<-EOT
    Azure VM family for driver and workers. Standard_DS3_v2 keeps the sandbox
    inside default DSv5 core quotas; memory-optimised families such as
    Standard_E8ds_v5 suit wide multi-country SCD2 merges.
  EOT
  type        = string
  default     = "Standard_DS3_v2"
}

variable "enable_photon" {
  description = <<-EOT
    Run the vectorised Photon engine. Worth enabling once the merge is wide
    enough to be scan-bound; on a single-node sandbox it costs DBUs without
    materially changing runtime.
  EOT
  type        = bool
  default     = false
}

variable "autotermination_minutes" {
  description = "Idle minutes before an interactive cluster on this policy self-terminates."
  type        = number
  default     = 20
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
