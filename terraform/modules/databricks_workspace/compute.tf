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
# data_security_mode is fixed, not defaulted. Row filters and column masks are
# not evaluated on SINGLE_USER compute, so a cluster that drifted off
# USER_ISOLATION would return unfiltered rows while appearing to work. Pinning
# it here means the guarantee survives someone editing the bundle.

locals {
  # A driver-only cluster must declare local execution explicitly; Spark
  # otherwise waits forever for workers that will never be requested.
  single_node_overrides = var.worker_count_max == 0 ? {
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
    } : {
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
  }

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
    "autotermination_minutes" = {
      type         = "range"
      minValue     = 10
      maxValue     = 120
      defaultValue = var.autotermination_minutes
    }
  }
}

resource "databricks_cluster_policy" "ingestion" {
  name       = "cp-sovereignshield-ingestion"
  definition = jsonencode(merge(local.base_policy, local.single_node_overrides))
}
