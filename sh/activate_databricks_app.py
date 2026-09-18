"""Activate one app snapshot, or reconcile a timed-out deployment by its exact ID."""

import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import AppDeployment, AppDeploymentMode


def state_value(status):
    state = getattr(status, "state", None)
    return getattr(state, "value", state)


def bundle_source_path(host, app_name, target):
    environment = dict(os.environ, DATABRICKS_HOST=host, DATABRICKS_AUTH_TYPE="azure-cli")
    result = subprocess.run(
        ["databricks", "bundle", "validate", "-t", target, "-o", "json"],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode:
        raise RuntimeError(f"Bundle source resolution failed for target {target}: {result.stderr.strip()}")
    configuration = json.loads(result.stdout)
    resource = configuration.get("resources", {}).get("apps", {}).get("sovereignshield_portal")
    if not resource or resource.get("name") != app_name:
        raise RuntimeError(f"Bundle target {target} does not configure sovereignshield_portal as {app_name}.")
    source_path = resource.get("source_code_path")
    if not isinstance(source_path, str) or not source_path.startswith("/Workspace/"):
        raise RuntimeError("The bundle app source did not resolve to a workspace path.")
    return source_path


def activate_app(workspace, app_name, *, source_code_path=None, resume=False, timeout_minutes=20):
    timeout = timedelta(minutes=timeout_minutes)
    app = workspace.apps.get(app_name)
    source_path = source_code_path or app.default_source_code_path
    if not source_path:
        raise RuntimeError("No app source path was supplied or recorded. Resolve the bundle source path before activation.")
    pending = app.pending_deployment
    deployment = pending
    if resume and deployment is None:
        deployments = list(workspace.apps.list_deployments(app_name))
        deployment = max(deployments, key=lambda item: (item.create_time or "", item.deployment_id or ""), default=None)
    if deployment is not None:
        if deployment.source_code_path != source_path:
            raise RuntimeError("The existing deployment does not match the configured bundle source path.")
        if state_value(deployment.status) in ("FAILED", "CANCELLED", "CANCELED", "STOPPED"):
            raise RuntimeError(f"Deployment {deployment.deployment_id} failed: {deployment.status.message}")
        print(f"Reconciling existing app deployment {deployment.deployment_id}.", flush=True)

    def report_app(current):
        print(f"App compute: {state_value(current.compute_status)}; app: {state_value(current.app_status)}", flush=True)

    if state_value(app.compute_status) != "ACTIVE":
        if state_value(app.compute_status) == "STOPPED":
            workspace.apps.start(app_name).result(timeout=timeout, callback=report_app)
        else:
            workspace.apps.wait_get_app_active(app_name, timeout=timeout, callback=report_app)
    if deployment is None:
        deployment = workspace.apps.deploy(app_name, AppDeployment(
            deployment_id=uuid4().hex, mode=AppDeploymentMode.SNAPSHOT, source_code_path=source_path,
        )).response
        print(f"Submitted app deployment {deployment.deployment_id} once.", flush=True)
    if not deployment.deployment_id:
        raise RuntimeError("Databricks returned no deployment ID; no additional deployment was submitted.")
    previous = None

    def report_deployment(current):
        nonlocal previous
        progress = (state_value(current.status), getattr(current.status, "message", None))
        if progress != previous:
            print(f"Deployment {current.deployment_id}: {progress[0]} - {progress[1] or ''}", flush=True)
            previous = progress
        if progress[0] in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Deployment {current.deployment_id} failed: {progress[1] or progress[0]}")

    try:
        workspace.apps.wait_get_deployment_app_succeeded(
            app_name, deployment.deployment_id, timeout=timeout, callback=report_deployment,
        )
    except TimeoutError as error:
        current = workspace.apps.get_deployment(app_name, deployment.deployment_id)
        report_deployment(current)
        if state_value(current.status) != "SUCCEEDED":
            raise RuntimeError(
                f"Deployment {deployment.deployment_id} did not complete within {timeout_minutes} minutes. "
                "It may still be running; resume with -StartAtStage 6 to reconcile it without redeploying."
            ) from error
    verified = workspace.apps.get(app_name)
    if (state_value(verified.app_status) != "RUNNING"
            or state_value(verified.compute_status) != "ACTIVE"
            or verified.pending_deployment is not None
            or verified.active_deployment is None
            or verified.active_deployment.deployment_id != deployment.deployment_id
            or state_value(verified.active_deployment.status) != "SUCCEEDED"):
        raise RuntimeError(f"Deployment {deployment.deployment_id} is not the healthy active deployment; resume Stage 6 after inspecting app status.")
    print(f"Verified active app deployment {deployment.deployment_id}: {verified.url}", flush=True)
    return deployment.deployment_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--target", default="dev")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout-minutes", type=int, choices=range(1, 61), default=20)
    args = parser.parse_args()
    print(f"Resolving app source from bundle target {args.target}.", flush=True)
    source_path = bundle_source_path(args.host, args.app_name, args.target)
    workspace = WorkspaceClient(host=args.host, auth_type="azure-cli")
    activate_app(
        workspace, args.app_name, source_code_path=source_path,
        resume=args.resume, timeout_minutes=args.timeout_minutes,
    )


if __name__ == "__main__":
    main()