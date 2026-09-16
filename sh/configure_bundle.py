"""Write the supported target-specific bundle overrides from non-secret outputs."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def write_overrides(root, target, cluster, run_as, warehouse):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", target):
        raise ValueError("Invalid bundle target.")
    if not isinstance(cluster, dict) or not cluster.get("policy_id"):
        raise ValueError("A governed cluster object with policy_id is required.")
    if not run_as or not warehouse:
        raise ValueError("Run-as and warehouse IDs are required.")
    path = Path(root) / ".databricks" / "bundle" / target / "variable-overrides.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    values.update(ingestion_cluster=cluster, run_as_service_principal=run_as, warehouse_id=warehouse)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="dev")
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--from-environment", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.from_environment:
        cluster = json.loads(os.environ["SOVEREIGNSHIELD_INGESTION_CLUSTER"])
        run_as = os.environ["BUNDLE_VAR_run_as_service_principal"]
        warehouse = os.environ["BUNDLE_VAR_warehouse_id"]
    else:
        def output(name):
            result = subprocess.run([
                args.terraform, f"-chdir={root / 'terraform'}", "output", "-json", name,
            ], capture_output=True, text=True, check=True)
            return json.loads(result.stdout)

        cluster = output("ingestion_job_cluster")
        run_as = output("cicd_client_id")
        warehouse = output("sql_warehouse_id")
    path = write_overrides(root, args.target, cluster, run_as, warehouse)
    print(f"Configured bundle overrides: {path.relative_to(root)}")


if __name__ == "__main__":
    main()