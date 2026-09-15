"""Inspect Terraform JSON without printing sensitive state or plan values."""

import argparse
import json
import sys


def resources(module):
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from resources(child)


def deployment_settings(state):
    entries = list(resources(state.get("values", {}).get("root_module", {})))
    addresses = [entry["address"] for entry in entries if entry.get("mode", "managed") == "managed"]
    accounts = any(".databricks_grant.catalog_traversal[" in address for address in addresses)
    tables = any(".databricks_grant.history_readers[" in address for address in addresses)
    gateway = any(address.startswith("module.dissemination_gateway[") for address in addresses)
    return {
        "mode": "steady-state" if accounts and tables else "bootstrap",
        "account_groups_ready": accounts or tables,
        "grant_tables": tables,
        "deploy_dissemination_gateway": gateway,
    }


def check_plan(plan, *, approve_compute_scale=False):
    for resource in plan.get("resource_changes", []):
        actions = resource.get("change", {}).get("actions", [])
        address = resource.get("address", "")
        if "delete" in actions:
            allowed_retirement = address == "module.identity.azuread_application_federated_identity_credential.github_pull_request" and actions == ["delete"]
            if not allowed_retirement:
                raise ValueError(f"Up/promotion refuses destructive change to {address}. Review an explicit migration or use down.")
        if actions == ["no-op"] or resource.get("type") != "databricks_cluster_policy":
            continue
        policy = json.loads((resource.get("change", {}).get("after") or {}).get("definition") or "{}")
        maximum = policy.get("autoscale.max_workers", {}).get("maxValue", 0)
        fixed = policy.get("num_workers", {}).get("value", 0)
        photon = policy.get("runtime_engine", {}).get("value") == "PHOTON"
        if (maximum > 0 or fixed > 0 or photon) and not approve_compute_scale:
            raise ValueError("Larger compute or Photon requires explicit -ApproveComputeScale approval.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["inspect", "check-plan"])
    parser.add_argument("--approve-compute-scale", action="store_true")
    args = parser.parse_args()
    document = json.load(sys.stdin)
    if args.operation == "inspect":
        print(json.dumps(deployment_settings(document)))
    else:
        check_plan(document, approve_compute_scale=args.approve_compute_scale)
        print("Plan passed non-destructive lifecycle and compute approval checks.")


if __name__ == "__main__":
    main()