from pathlib import Path
import importlib.util
import json

import pytest

import yaml

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("deployment_state", ROOT / "sh/deployment_state.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


def test_pull_requests_have_no_cloud_authentication_job():
    workflow = yaml.load((ROOT / ".github/workflows/promote.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"]["workflow_dispatch"]["inputs"]["operation"]["default"] == "verify"
    assert workflow["jobs"]["verify"]["permissions"] == {"contents": "read"}
    for name in ("plan", "apply"):
        job = workflow["jobs"][name]
        assert "workflow_dispatch" in job["if"]
        assert "refs/heads/main" in job["if"]
        assert job["environment"] == "production"
    assert workflow["jobs"]["bundle"]["needs"] == "apply"
    assert "Require an active human approval gate" in [step.get("name") for step in workflow["jobs"]["preflight"]["steps"]]
    for name in ("plan", "apply"):
        assert any("sh/ci_terraform.py" in step.get("run", "") for step in workflow["jobs"][name]["steps"])


def test_deployment_identity_has_no_pull_request_federation():
    source = (ROOT / "terraform/modules/identity/main.tf").read_text(encoding="utf-8")
    assert "github_pull_request" not in source
    assert ':pull_request"' not in source
    assert ':environment:${var.github_environment}"' in source


def state(*addresses):
    return {"values": {"root_module": {"child_modules": [{"resources": [{"address": address} for address in addresses]}]}}}


def test_fresh_bootstrap_starts_without_grants():
    settings = deployment.deployment_settings({})
    assert settings == {"mode": "bootstrap", "account_groups_ready": False, "grant_tables": False, "deploy_dissemination_gateway": False}


def test_steady_state_preserves_existing_grants_and_gateway():
    settings = deployment.deployment_settings(state(
        'module.unity_catalog_governance.databricks_grant.catalog_traversal["admin"]',
        'module.unity_catalog_governance.databricks_grant.history_readers["public"]',
        'module.dissemination_gateway[0].azurerm_container_app.portal',
    ))
    assert settings["mode"] == "steady-state"
    assert settings["account_groups_ready"] and settings["grant_tables"] and settings["deploy_dissemination_gateway"]


def test_partial_bootstrap_does_not_reset_ready_accounts():
    settings = deployment.deployment_settings(state('module.unity_catalog_governance.databricks_grant.catalog_traversal["admin"]'))
    assert settings["mode"] == "bootstrap" and settings["account_groups_ready"] and not settings["grant_tables"]


def test_up_refuses_deleting_established_resources():
    plan = {"resource_changes": [{"address": "module.unity_catalog_governance.databricks_grant.history_readers", "change": {"actions": ["delete"]}}]}
    with pytest.raises(ValueError, match="refuses destructive"):
        deployment.check_plan(plan)


def test_obsolete_pr_federation_can_be_retired():
    deployment.check_plan({"resource_changes": [{
        "address": "module.identity.azuread_application_federated_identity_credential.github_pull_request",
        "change": {"actions": ["delete"]},
    }]})


def test_larger_compute_is_opt_in():
    plan = {"resource_changes": [{"type": "databricks_cluster_policy", "change": {
        "actions": ["update"], "after": {"definition": json.dumps({"autoscale.max_workers": {"maxValue": 2}})},
    }}]}
    with pytest.raises(ValueError, match="ApproveComputeScale"):
        deployment.check_plan(plan)
    deployment.check_plan(plan, approve_compute_scale=True)


def test_bundle_has_no_duplicate_keys_and_uses_governed_compute():
    class UniqueLoader(yaml.SafeLoader):
        pass

    def unique_mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            assert key not in result, f"Duplicate YAML key: {key}"
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
    bundle = yaml.load((ROOT / "databricks.yml").read_text(encoding="utf-8"), Loader=UniqueLoader)
    job = bundle["targets"]["dev"]["resources"]["jobs"]["sovereignshield_sdmx_pipeline"]
    assert job["max_concurrent_runs"] == 1
    assert job["run_as"]["service_principal_name"] == "${var.run_as_service_principal}"
    assert job["job_clusters"][0]["new_cluster"] == "${var.ingestion_cluster}"