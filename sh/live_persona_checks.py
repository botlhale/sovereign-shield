"""Exercise real UC entitlements with temporary identities and revoke them afterward."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

import requests
from databricks.sdk import AccountClient, WorkspaceClient
from databricks.sdk.service.iam import AccessControlRequest, ComplexValue, Patch, PatchOp, PermissionLevel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uc_query import DatabricksBackend, Principal, SeriesFilter, build_search_sql

GROUPS = {
    "public": ("public",),
    "researcher": ("researchers",),
    "submitter-ca": ("submitter-ca",),
    "submitter-us": ("submitter-us",),
    "admin": ("admin",),
    "dual-ca-researcher": ("submitter-ca", "researchers"),
    "unaffiliated": (),
}


def assert_persona(name, frame):
    country = frame["TIME_SERIES_CODE"].str.split(".").str[8]
    restricted = ~frame["OBS_CONF"].eq("F")
    if name == "unaffiliated":
        assert frame.empty, "Unaffiliated principal received rows"
        return
    assert not frame.empty, f"{name} received no fixture rows"
    if name == "public":
        assert len(frame) == 13
        assert frame["BATCH_STATUS"].eq("PUBLISHED").all()
        assert not restricted.any()
        assert frame["OBS_VALUE"].notna().all()
    elif name == "researcher":
        assert len(frame) == 22
        assert frame["BATCH_STATUS"].eq("PUBLISHED").all()
        assert frame.loc[restricted, "OBS_VALUE"].isna().all()
        assert restricted.sum() == 9
    elif name.startswith("submitter-"):
        own = country.eq(name[-2:].upper())
        assert frame.loc[own, "OBS_VALUE"].notna().all()
        assert frame.loc[~own, "BATCH_STATUS"].eq("PUBLISHED").all()
        assert frame.loc[~own, "OBS_CONF"].eq("F").all()
        rejected = frame[own & frame["BATCH_STATUS"].eq("QUARANTINE")]
        assert len(rejected) == 4
        assert rejected["BATCH_FAILED_RULE_ID"].notna().all()
    elif name == "admin":
        assert len(frame) == 44
        assert frame["OBS_VALUE"].notna().all()
        assert frame["BATCH_STATUS"].eq("QUARANTINE").sum() == 22
    else:
        foreign_restricted = frame[~country.eq("CA") & restricted]
        assert not foreign_restricted.empty
        assert foreign_restricted["OBS_VALUE"].isna().all()
        assert frame.loc[country.eq("CA"), "OBS_VALUE"].notna().all()
        assert frame[country.eq("CA") & frame["BATCH_STATUS"].eq("QUARANTINE")].shape[0] == 4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--warehouse", required=True)
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args()
    workspace = WorkspaceClient(host=args.host, auth_type="azure-cli")
    account = AccountClient(host="https://accounts.azuredatabricks.net", account_id=args.account_id, auth_type="azure-cli")
    backend = DatabricksBackend()
    backend.hostname = args.host.removeprefix("https://").rstrip("/")
    backend.http_path = f"/sql/1.0/warehouses/{args.warehouse}"
    groups = {group.display_name: str(group.id) for group in account.groups.list() if group.display_name}
    sql, parameters = build_search_sql(SeriesFilter.build(lifecycle="all", limit=500))
    evidence = []
    temporary = []
    try:
        for name, memberships in GROUPS.items():
            principal = workspace.service_principals.create(
                display_name=f"ss-live-check-{name}-{uuid4().hex[:10]}",
                entitlements=[ComplexValue(value="databricks-sql-access")],
            )
            temporary.append({"id": str(principal.id), "secret_id": None, "groups": [], "grants": [], "application_id": principal.application_id})
            cleanup = temporary[-1]
            application_id = principal.application_id
            if not application_id:
                raise RuntimeError("Test principal has no application ID")
            for suffix in memberships:
                group_id = groups[f"sg-sovereignshield-{suffix}"]
                account.groups.patch(group_id, operations=[Patch(op=PatchOp.ADD, path="members", value=[{"value": str(principal.id)}])])
                cleanup["groups"].append(group_id)
            workspace.permissions.update("sql/warehouses", args.warehouse, access_control_list=[AccessControlRequest(service_principal_name=application_id, permission_level=PermissionLevel.CAN_USE)])
            secret = account.service_principal_secrets.create(str(principal.id), lifetime="3600s")
            cleanup["secret_id"] = secret.id
            response = requests.post(
                args.host.rstrip("/") + "/oidc/v1/token",
                auth=(application_id, secret.secret),
                data={"grant_type": "client_credentials", "scope": "all-apis"}, timeout=30,
            )
            if response.status_code != 200:
                raise RuntimeError(f"Test OAuth authentication failed with HTTP {response.status_code}.")
            access_token = response.json()["access_token"]
            if name == "unaffiliated":
                from databricks.sdk.service.catalog import PermissionsChange, Privilege
                for kind, target, privileges in (
                    ("catalog", "dbw_sovereignshield", [Privilege.USE_CATALOG]),
                    ("schema", "dbw_sovereignshield.sovereign_shield", [Privilege.USE_SCHEMA, Privilege.EXECUTE]),
                    ("table", "dbw_sovereignshield.sovereign_shield.agg_sdmx_history", [Privilege.SELECT]),
                ):
                    workspace.grants.update(kind, target, changes=[PermissionsChange(principal=application_id, add=privileges)])
                    cleanup["grants"].append((kind, target, privileges))
            identity = Principal(display_name=name, groups=frozenset(f"sg-sovereignshield-{suffix}" for suffix in memberships), authenticated=True, access_token=access_token)
            frame = backend.query(sql, parameters, identity)
            assert_persona(name, frame)
            evidence.append({"persona": name, "rows": len(frame), "masked": int(frame["OBS_VALUE"].isna().sum())})
            print(json.dumps(evidence[-1]), flush=True)
            account.service_principal_secrets.delete(str(principal.id), cleanup["secret_id"])
            cleanup["secret_id"] = None
            del secret, access_token, identity, response
        print("LIVE_PERSONA_ACCEPTANCE_PASSED", flush=True)
    finally:
        failures = []
        for item in reversed(temporary):
            if item["secret_id"]:
                try:
                    account.service_principal_secrets.delete(item["id"], item["secret_id"])
                except Exception as error:
                    failures.append(f"OAuth secret cleanup for {item['id']}: {type(error).__name__}")
            for kind, target, privileges in reversed(item["grants"]):
                try:
                    workspace.grants.update(kind, target, changes=[PermissionsChange(principal=item["application_id"], remove=privileges)])
                except Exception as error:
                    failures.append(f"Grant cleanup for {item['id']}: {type(error).__name__}")
            for group_id in item["groups"]:
                try:
                    account.groups.patch(group_id, operations=[Patch(op=PatchOp.REMOVE, path=f'members[value eq "{item["id"]}"]')])
                except Exception as error:
                    failures.append(f"Group cleanup for {item['id']}: {type(error).__name__}")
            try:
                account.service_principals.delete(item["id"])
            except Exception as error:
                failures.append(f"Identity cleanup for {item['id']}: {type(error).__name__}")
        if failures:
            raise RuntimeError("Test identity cleanup needs attention: " + "; ".join(failures))
        print(f"Removed {len(temporary)} temporary test principals and their OAuth secrets.", flush=True)


if __name__ == "__main__":
    main()