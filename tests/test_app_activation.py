from pathlib import Path
import importlib.util
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from databricks.sdk.service.apps import App, AppDeployment


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("activate_databricks_app", ROOT / "sh/activate_databricks_app.py")
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)
SOURCE = "/Workspace/SovereignShield/dev/files/src"


def test_stage6_assigns_public_identity_before_one_deployment():
    source = (ROOT / "sh/sovereignshield_up.ps1").read_text(encoding="utf-8")
    stage = source.split('Invoke-Stage 6 "Databricks App activation" {', 1)[1].split('Invoke-Stage 7 ', 1)[0]
    assert '"bundle", "run", "sovereignshield_portal"' not in stage
    assert stage.count("sh/activate_databricks_app.py") == 1
    assert stage.index("-AppOnly") < stage.index("sh/activate_databricks_app.py")
    assert 'if ($StartAtStage -eq 6) { $activationArguments += "--resume" }' in stage


def deployment(identity="latest", state="SUCCEEDED", created="2026-09-18T15:52:12Z"):
    return AppDeployment.from_dict({
        "deployment_id": identity,
        "source_code_path": SOURCE,
        "create_time": created,
        "status": {"state": state, "message": "test state"},
    })


def app(active=None, pending=None):
    return App.from_dict({
        "name": "portal",
        "default_source_code_path": SOURCE,
        "active_deployment": active.as_dict() if active else None,
        "pending_deployment": pending.as_dict() if pending else None,
        "app_status": {"state": "RUNNING"},
        "compute_status": {"state": "ACTIVE"},
        "url": "https://portal.example.test",
    })


def client(initial, final, latest):
    api = Mock()
    api.get.side_effect = [initial, final]
    api.list_deployments.return_value = [latest]
    api.wait_get_deployment_app_succeeded.return_value = latest
    return SimpleNamespace(apps=api)


def test_success_after_cli_timeout_is_reconciled_without_redeployment():
    latest = deployment()
    workspace = client(app(latest), app(latest), latest)
    assert activation.activate_app(workspace, "portal", resume=True) == "latest"
    workspace.apps.deploy.assert_not_called()
    workspace.apps.start.assert_not_called()
    assert workspace.apps.wait_get_deployment_app_succeeded.call_args.args == ("portal", "latest")


def test_pending_deployment_is_waited_not_replaced():
    pending = deployment(state="IN_PROGRESS")
    workspace = client(app(deployment("old"), pending), app(deployment()), pending)
    activation.activate_app(workspace, "portal")
    workspace.apps.deploy.assert_not_called()


def test_failed_latest_deployment_cannot_use_older_healthy_app():
    failed = deployment(state="FAILED")
    workspace = client(app(deployment("old")), app(deployment("old")), failed)
    with pytest.raises(RuntimeError, match="Deployment latest failed"):
        activation.activate_app(workspace, "portal", resume=True)
    workspace.apps.deploy.assert_not_called()


def test_timeout_checks_exact_deployment_and_recovers_success():
    latest = deployment()
    workspace = client(app(pending=deployment(state="IN_PROGRESS")), app(latest), latest)
    workspace.apps.wait_get_deployment_app_succeeded.side_effect = TimeoutError()
    workspace.apps.get_deployment.return_value = latest
    assert activation.activate_app(workspace, "portal", resume=True) == "latest"
    workspace.apps.get_deployment.assert_called_once_with("portal", "latest")


def test_unfinished_timeout_stays_a_failure_and_never_redeploys():
    pending = deployment(state="IN_PROGRESS")
    workspace = client(app(pending=pending), app(), pending)
    workspace.apps.wait_get_deployment_app_succeeded.side_effect = TimeoutError()
    workspace.apps.get_deployment.return_value = pending
    with pytest.raises(RuntimeError, match="resume with -StartAtStage 6"):
        activation.activate_app(workspace, "portal", resume=True)
    workspace.apps.deploy.assert_not_called()


def test_different_active_deployment_is_not_success():
    workspace = client(app(deployment()), app(deployment("different")), deployment())
    with pytest.raises(RuntimeError, match="not the healthy active deployment"):
        activation.activate_app(workspace, "portal", resume=True)


def test_fresh_activation_submits_once():
    latest = deployment()
    workspace = client(app(deployment("old")), app(latest), latest)
    workspace.apps.deploy.return_value = SimpleNamespace(response=latest)
    activation.activate_app(workspace, "portal")
    workspace.apps.deploy.assert_called_once()
    assert workspace.apps.deploy.call_args.args[1].source_code_path == SOURCE


def test_stopped_compute_is_started_before_one_deployment():
    latest = deployment()
    initial = app()
    initial.compute_status = App.from_dict({"compute_status": {"state": "STOPPED"}}).compute_status
    workspace = client(initial, app(latest), latest)
    workspace.apps.deploy.return_value = SimpleNamespace(response=latest)
    activation.activate_app(workspace, "portal", timeout_minutes=7)
    workspace.apps.start.assert_called_once_with("portal")
    assert workspace.apps.start.return_value.result.call_args.kwargs["timeout"].total_seconds() == 420
    method_names = [call[0] for call in workspace.apps.mock_calls]
    assert method_names.index("start().result") < method_names.index("deploy")


@pytest.mark.parametrize("state", ["FAILED", "CANCELLED"])
def test_deployment_failure_during_wait_is_propagated_immediately(state):
    pending = deployment(state="IN_PROGRESS")
    workspace = client(app(pending=pending), app(), pending)

    def fail_during_wait(app_name, deployment_id, *, timeout, callback):
        callback(deployment(state=state))

    workspace.apps.wait_get_deployment_app_succeeded.side_effect = fail_during_wait
    with pytest.raises(RuntimeError, match="Deployment latest failed"):
        activation.activate_app(workspace, "portal", resume=True)
    workspace.apps.deploy.assert_not_called()
    assert workspace.apps.get.call_count == 1


def test_resume_selects_latest_by_timestamp_not_list_order():
    latest = deployment(state="FAILED")
    older = deployment("old", created="2026-09-18T15:51:33Z")
    workspace = client(app(older), app(older), latest)
    workspace.apps.list_deployments.return_value = [older, latest]
    with pytest.raises(RuntimeError, match="Deployment latest failed"):
        activation.activate_app(workspace, "portal", resume=True)
    workspace.apps.deploy.assert_not_called()


def test_resume_rejects_another_source_path():
    latest = deployment()
    latest.source_code_path = "/Workspace/another-bundle/files/src"
    workspace = client(app(latest), app(latest), latest)
    with pytest.raises(RuntimeError, match="does not match"):
        activation.activate_app(workspace, "portal", resume=True)
    workspace.apps.deploy.assert_not_called()