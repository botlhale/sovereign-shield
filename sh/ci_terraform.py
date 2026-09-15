"""Reviewed steady-state promotion; bootstrap uses the up orchestration command."""

import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path

from deployment_state import check_plan, deployment_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["plan", "apply"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    prefix = ["terraform", f"-chdir={root / 'terraform'}"]

    def execute(arguments, *, capture=False):
        result = subprocess.run(prefix + arguments, check=True, text=True, capture_output=capture)
        return result.stdout if capture else None

    backend = {
        "resource_group_name": os.environ["TF_STATE_RESOURCE_GROUP"],
        "storage_account_name": os.environ["TF_STATE_STORAGE_ACCOUNT"],
        "container_name": os.environ["TF_STATE_CONTAINER"],
        "key": "sovereignshield.tfstate", "use_azuread_auth": "true",
    }
    execute(["init", "-input=false"] + [f"-backend-config={name}={value}" for name, value in backend.items()])
    settings = deployment_settings(json.loads(execute(["show", "-json"], capture=True)))
    if settings["mode"] != "steady-state":
        raise RuntimeError("Complete the approved bootstrap with sovereignshield_up before CI promotion.")
    plan_name = f".sovereignshield-ci-{uuid.uuid4().hex}.tfplan"
    try:
        flags = [f"-var={name}={str(settings[name]).lower()}" for name in ("account_groups_ready", "grant_tables", "deploy_dissemination_gateway")]
        execute(["plan", "-no-color", "-input=false", f"-out={plan_name}"] + flags)
        plan = json.loads(execute(["show", "-json", plan_name], capture=True))
        check_plan(plan)
        if args.operation == "apply":
            execute(["apply", "-input=false", plan_name])
        output_file = os.getenv("GITHUB_OUTPUT")
        if output_file:
            outputs = json.loads(execute(["output", "-json"], capture=True))
            with open(output_file, "a", encoding="utf-8") as output:
                for name, target in (("sql_warehouse_id", "warehouse_id"), ("cicd_client_id", "run_as"), ("ingestion_job_cluster", "cluster")):
                    value = outputs[name]["value"]
                    output.write(f"{target}={json.dumps(value, separators=(',', ':')) if isinstance(value, dict) else value}\n")
    finally:
        (root / "terraform" / plan_name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()