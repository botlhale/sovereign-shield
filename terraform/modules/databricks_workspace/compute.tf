# Compute sizing envelope for the ingestion and SCD2 merge workload.
#
# OWNERSHIP BOUNDARY
# Terraform owns the *policy*, the bundle owns the *job*. A cluster policy is
# infrastructure governance: it fixes the security posture and bounds the size.
# databricks.yml then declares a job cluster that inherits from it. Terraform
# never declares the job itself, so the two planes cannot fight over the same
# object.
#
# The policy is what makes single-node a *default* rather than a constraint.
# Raising worker_count_max and setting enable_photon widens the envelope
# without touching a line of pipeline code.
#
# This deployment fixes USER_ISOLATION. Dedicated compute has separate runtime
# and serverless requirements; it is not a universal row-policy bypass.

locals {
  # A driver-only cluster must declare local execution explicitly; Spark
  # otherwise waits forever for workers that will never be requested.
  single_node_overrides = jsondecode(var.worker_count_max == 0 ? jsonencode({
    "spark_conf.spark.master" = {
      type  = "fixed"
      value = "local[*, 4]"
    }
    "spark_conf.spark.databricks.cluster.profile" = {
      type  = "fixed"
      value = "singleNode"
    }
    "custom_tags.ResourceClass" = {
      type  = "fixed"
      value = "SingleNode"
    }
    "num_workers" = {
      type  = "fixed"
      value = 0
    }
    }) : jsonencode({
    "autoscale.min_workers" = {
      type         = "range"
      minValue     = var.worker_count_min
      maxValue     = var.worker_count_max
      defaultValue = var.worker_count_min
    }
    "autoscale.max_workers" = {
      type         = "range"
      minValue     = var.worker_count_min
      maxValue     = var.worker_count_max
      defaultValue = var.worker_count_max
    }
  }))

  base_policy = {
    "data_security_mode" = {
      type  = "fixed"
      value = "USER_ISOLATION"
    }
    "node_type_id" = {
      type  = "fixed"
      value = var.node_type_id
    }
    "runtime_engine" = {
      type  = "fixed"
      value = var.enable_photon ? "PHOTON" : "STANDARD"
    }
    "spark_version" = {
      type    = "regex"
      pattern = "^1[0-9]+\\..*"
    }
    # Spot with on-demand fallback: a reclaimed node retries rather than
    # failing the submission batch mid-merge.
    "azure_attributes.availability" = {
      type  = "fixed"
      value = "SPOT_WITH_FALLBACK_AZURE"
    }
    "cluster_type" = {
      type  = "fixed"
      value = "job"
    }
  }
}

resource "databricks_cluster_policy" "ingestion" {
  name       = "cp-sovereignshield-ingestion"
  definition = jsonencode(merge(local.base_policy, local.single_node_overrides))
}

output "ingestion_job_cluster" {
  value = merge({
    policy_id                   = databricks_cluster_policy.ingestion.id
    apply_policy_default_values = true
    spark_version               = "18.x-scala2.13"
    node_type_id                = var.node_type_id
    data_security_mode          = "USER_ISOLATION"
    runtime_engine              = var.enable_photon ? "PHOTON" : "STANDARD"
    azure_attributes            = { availability = "SPOT_WITH_FALLBACK_AZURE" }
    }, var.worker_count_max == 0 ? {
    num_workers = 0
    } : {}, var.worker_count_max == 0 ? {
    spark_conf  = { "spark.databricks.cluster.profile" = "singleNode", "spark.master" = "local[*, 4]" }
    custom_tags = { ResourceClass = "SingleNode" }
    } : {}, var.worker_count_max > 0 ? {
    autoscale = { min_workers = var.worker_count_min, max_workers = var.worker_count_max }
  } : {})
}
