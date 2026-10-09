from pathlib import Path
import importlib.util
import json
import re

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


def test_readiness_reads_terraform_without_a_powershell_stdin_pipe(monkeypatch, capsys):
    from types import SimpleNamespace

    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps(state('module.unity_catalog_governance.databricks_grant.catalog_traversal["admin"]')))

    monkeypatch.setattr(deployment.subprocess, "run", run)
    monkeypatch.setattr(deployment.sys, "argv", ["deployment_state.py", "inspect", "--terraform", "terraform.exe", "--directory", "project/terraform"])
    deployment.main()
    assert json.loads(capsys.readouterr().out)["account_groups_ready"] is True
    assert calls == [(["terraform.exe", "-chdir=project/terraform", "show", "-json"], {"capture_output": True, "text": True, "check": True})]


def test_az_databricks_extension_is_installed_before_first_use():
    """Without the extension az asks to install it, and captured output hides that prompt."""
    scripts = [path for path in (ROOT / "sh").glob("*.ps1") if "az databricks " in path.read_text(encoding="utf-8")]
    assert scripts
    for path in scripts:
        source = path.read_text(encoding="utf-8")
        install = source.find("Install-SovereignShieldAzExtension -Name databricks")
        assert 0 <= install < source.index("az databricks "), path.name


def _section(source, start, end):
    """The text from start up to end; each marker must occur exactly once."""
    assert source.count(start) == 1 and source.count(end) == 1, (start, end)
    assert source.index(start) < source.index(end)
    return source[source.index(start):source.index(end)]


def test_teardown_force_deletes_the_workspace_and_skips_deleting_ones():
    """Without force_delete Azure keeps the default UC storage and the workspace stays Deleting (25058f8)."""
    providers = (ROOT / "terraform/providers.tf").read_text(encoding="utf-8")
    assert re.search(r"databricks_workspace\s*\{[^}]*\bforce_delete\s*=\s*true", providers)
    module = (ROOT / "terraform/modules/databricks_workspace/main.tf").read_text(encoding="utf-8")
    timeout = re.search(r"timeouts\s*\{[^}]*\bdelete\s*=\s*\"(\d+)m\"", module)
    assert timeout and int(timeout.group(1)) >= 60
    down = (ROOT / "sh/sovereignshield_down.ps1").read_text(encoding="utf-8")
    discovery = down[:down.index("Set-SovereignShieldWorkspaceAuth")]
    assert "provisioningState=='Succeeded'" in discovery


def test_down_waits_out_an_in_progress_workspace_delete_before_terraform_destroy():
    """A second delete fails with ApplianceBeingDeleted, and az wait exits 0 on timeout (b7e7d33)."""
    down = (ROOT / "sh/sovereignshield_down.ps1").read_text(encoding="utf-8")
    destroy = _section(down, 'Start-TimedStep "Terraform destroy"', '"destroy", "-input=false"')
    wait = destroy.find("workspace wait --deleted")
    assert wait >= 0
    after_wait = destroy[wait:]
    assert "@workspaceStateQuery" in after_wait and "throw" in after_wait


def test_stage1_retry_waits_for_sql_access_with_a_deadline():
    """A new workspace grants its admins databricks-sql-access minutes after creation (1e744d0)."""
    up = (ROOT / "sh/sovereignshield_up.ps1").read_text(encoding="utf-8")
    retry = _section(up, "Foundation apply stopped after workspace creation", 'Invoke-Stage 2 "')
    poll = retry.find("databricks warehouses list")
    reapply = retry.rfind("Invoke-SovereignShieldTerraformApply")
    assert 0 <= poll < reapply
    assert "$deadline" in retry[:poll] and "throw" in retry[poll:reapply]


def test_down_waits_until_azure_removes_the_container_apps_environment():
    """az containerapp env delete stops polling after about 20 minutes; Azure took 27 (7810503)."""
    down = (ROOT / "sh/sovereignshield_down.ps1").read_text(encoding="utf-8")
    gateway = _section(down, '"containerapp", "env", "delete"', "az acr list")
    for evidence in ("Microsoft.App/managedEnvironments", "az group exists", "$deadline", "throw"):
        assert evidence in gateway, evidence


def test_up_preflight_runs_on_linux_and_tests_before_taking_the_lock():
    """No Windows-only Python path (0e5b228); the suite runs before the flock, held before Azure changes (c38f3a7)."""
    up = (ROOT / "sh/sovereignshield_up.ps1").read_text(encoding="utf-8")
    assert r"Scripts\python.exe" not in up
    stage0 = _section(up, 'Invoke-Stage 0 "Preflight and offline verification"', "if ($StopAfterStage -eq 0) { return }")
    assert "Get-SovereignShieldPython" in stage0
    suite, lock = stage0.index('"-m", "pytest"'), stage0.index("Enter-SovereignShieldLifecycleLock")
    assert suite < lock < stage0.index('"provider", "register"')
    resumed = _section(up, "if ($StopAfterStage -eq 0) { return }", 'Invoke-Stage 1 "')
    assert "Enter-SovereignShieldLifecycleLock" in resumed, "a run that starts after Stage 0 still takes the lock"


def test_down_stops_when_an_azure_cli_query_fails():
    """A failed az query returned nothing, which read as "already gone" and let teardown skip ahead (c38f3a7)."""
    down = (ROOT / "sh/sovereignshield_down.ps1").read_text(encoding="utf-8")
    discovery = down[:down.index("Set-SovereignShieldWorkspaceAuth")]
    assert "if ($LASTEXITCODE -ne 0) { throw" in discovery[discovery.index("provisioningState=='Succeeded'"):]
    gateway = _section(down, '"containerapp", "env", "delete"', "az acr list")
    assert '$LASTEXITCODE -ne 0 -or $groupExists -notin @("true", "false")' in gateway
    destroy = _section(down, 'Start-TimedStep "Terraform destroy"', '"destroy", "-input=false"')
    assert destroy.count("& az @workspaceStateQuery") == destroy.count("if ($LASTEXITCODE -ne 0) { throw") == 2


def test_orchestration_module_exports_every_function_the_scripts_call():
    """An unexported function fails only when a lifecycle run reaches the call, often in finally."""
    module = (ROOT / "sh/lib/SovereignShield.Orchestration.psm1").read_text(encoding="utf-8")
    defined = set(re.findall(r"^function ([\w-]+)", module, re.MULTILINE))
    exported = set(re.findall(r'"([\w-]+)"', module.split("Export-ModuleMember", 1)[1]))
    called = set()
    for path in (ROOT / "sh").glob("*.ps1"):
        called |= defined & set(re.findall(r"[\w]+-SovereignShield\w*", path.read_text(encoding="utf-8")))
    assert called and called <= exported, sorted(called - exported)


def test_easy_auth_requests_the_databricks_scope_from_any_shell():
    """JSON quotes reached az under Linux pwsh, so Entra issued Graph tokens and every persona got 401 (2026-10-08)."""
    deploy = (ROOT / "sh/container_apps_deploy.ps1").read_text(encoding="utf-8")
    login = _section(deploy, "$expectedLoginParameter =", "--token-store true")
    assert login.startswith(
        '$expectedLoginParameter = "scope=openid profile offline_access $AzureDatabricksResourceId/user_impersonation"')
    assert 'loginParameters=[$expectedLoginParameter]"' in login
    readback = login[login.index("az containerapp auth show"):]
    assert "$storedLoginParameters[0] -ne $expectedLoginParameter" in readback and "throw" in readback


def test_easy_auth_scopes_are_declared_once_and_admin_consented():
    """Each run appended the same permission again, and offline_access had no admin consent (2026-10-08)."""
    deploy = (ROOT / "sh/container_apps_deploy.ps1").read_text(encoding="utf-8")
    entra = _section(deploy, "if ($EnableEntraSignIn) {", "$expectedLoginParameter =")
    assert entra.index("-notcontains $UserImpersonationScopeId") < entra.index("az ad app permission add")
    graph = entra.index("--api $MicrosoftGraphResourceId")
    command = entra[entra.rindex("az ad app permission grant", 0, graph):entra.index("$LASTEXITCODE", graph)]
    assert '--scope "openid profile email offline_access"' in command


def test_readiness_checks_the_scope_the_live_sign_in_requests():
    """A stored parameter can look right while Entra receives another scope (2026-10-08)."""
    up = (ROOT / "sh/sovereignshield_up.ps1").read_text(encoding="utf-8")
    readiness = _section(up, 'Invoke-Stage 8 "', "if ($ConfigureGitHub)")
    check = readiness[readiness.index("AllowAutoRedirect = $false"):]
    assert "/.auth/login/aad" in check
    assert "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/user_impersonation" in check and "throw" in check


def test_empty_native_terraform_output_fails_closed(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(deployment.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    monkeypatch.setattr(deployment.sys, "argv", ["deployment_state.py", "inspect", "--terraform", "terraform.exe"])
    with pytest.raises(RuntimeError, match="returned no JSON"):
        deployment.main()


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


@pytest.mark.parametrize("workers", [0, "0"])
def test_single_node_plan_accepts_numeric_and_string_worker_counts(workers):
    deployment.check_plan({"resource_changes": [{"type": "databricks_cluster_policy", "change": {
        "actions": ["create"], "after": {"definition": json.dumps({"num_workers": {"value": workers}})},
    }}]})


@pytest.mark.parametrize("workers", ["2", "invalid", None, True, -1, "0.5"])
def test_encoded_worker_counts_cannot_bypass_cost_guard(workers):
    plan = {"resource_changes": [{"type": "databricks_cluster_policy", "change": {
        "actions": ["create"], "after": {"definition": json.dumps({"num_workers": {"value": workers}})},
    }}]}
    with pytest.raises(ValueError):
        deployment.check_plan(plan)


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
    assert bundle["targets"]["dev"]["mode"] == "production"
    assert bundle["targets"]["dev"]["permissions"] == [{"group_name": "sg-sovereignshield-admin", "level": "CAN_MANAGE"}]
    assert "/Workspace/Shared" not in bundle["targets"]["dev"]["workspace"]["root_path"]
    job = bundle["targets"]["dev"]["resources"]["jobs"]["sovereignshield_sdmx_pipeline"]
    assert job["max_concurrent_runs"] == 1
    assert job["run_as"]["service_principal_name"] == "${var.run_as_service_principal}"
    assert job["job_clusters"][0]["new_cluster"] == "${var.ingestion_cluster}"