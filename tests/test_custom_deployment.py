"""Bring-your-own-estate scripts: attach what exists, create only the delta, remove only that.

The scripts run unchanged against stub ``az`` and ``databricks`` executables that keep
a small in-memory estate, so the provenance and teardown rules are checked offline.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "scripts" / "sovereign_up_custom.sh"
DOWN = ROOT / "scripts" / "sovereign_down_custom.sh"
TAGS = ("ManagedBy=SovereignShield", "ProvisionedScope=Delta")

pytestmark = pytest.mark.skipif(
    not (shutil.which("bash") and shutil.which("jq")), reason="the custom scripts need bash and jq"
)

STUB = r'''
import json, os, sys, uuid
from pathlib import Path

state_path = Path(os.environ["SS_STUB_STATE"])
tool, argv = sys.argv[1], sys.argv[2:]
with open(os.environ["SS_STUB_LOG"], "a") as log:
    log.write(json.dumps([tool] + argv) + "\n")
state = json.loads(state_path.read_text())
sub = state["subscription"]

positional, options, index = [], {}, 0
while index < len(argv):
    token = argv[index]
    index += 1
    if token.startswith("-"):
        values = []
        while index < len(argv) and not argv[index].startswith("-"):
            values.append(argv[index])
            index += 1
        options[token] = values
    else:
        positional.append(token)

def opt(name):
    return (options.get(name) or [None])[0]

def done(payload=None):
    state_path.write_text(json.dumps(state))
    if payload is not None:
        print(json.dumps(payload))
    sys.exit(0)

def missing():
    print("ResourceNotFound", file=sys.stderr)
    sys.exit(1)

def tags():
    return dict(item.split("=", 1) for item in options.get("--tags", []))

def view(rid):
    resource = state["resources"][rid]
    return {"id": rid, "name": resource["name"], "tags": resource["tags"], **resource.get("props", {})}

def find(provider, name, rg=None):
    for rid, resource in state["resources"].items():
        if resource["provider"] == provider and resource["name"] == name and rg in (None, resource["rg"]):
            return rid
    return None

def create(provider, name, rg, props=None):
    rid = f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/{name}"
    state["resources"][rid] = {"provider": provider, "name": name, "rg": rg, "tags": tags(), "props": props or {}}
    done(view(rid))

def azure():
    path = tuple(positional)
    providers = {
        ("keyvault",): "Microsoft.KeyVault/vaults",
        ("storage", "account"): "Microsoft.Storage/storageAccounts",
        ("databricks", "workspace"): "Microsoft.Databricks/workspaces",
        ("databricks", "access-connector"): "Microsoft.Databricks/accessConnectors",
    }
    if path == ("account", "show"):
        print(sub) if opt("--query") == "id" else print(json.dumps({"id": sub}))
        sys.exit(0)
    if path in (("account", "set"), ("extension", "add")):
        done()
    if path[0] == "group":
        name = opt("--name")
        if path[1] == "show":
            group = state["groups"].get(name) or missing()
            done({"id": f"/subscriptions/{sub}/resourceGroups/{name}", "name": name, "location": "canadacentral", "tags": group["tags"]})
        if path[1] == "create":
            state["groups"][name] = {"tags": tags()}
            done({"id": f"/subscriptions/{sub}/resourceGroups/{name}", "name": name, "location": opt("--location")})
        if path[1] == "delete":
            assert not any(r["rg"] == name for r in state["resources"].values()), "deleted a non-empty group"
            del state["groups"][name]
            done()
    for prefix, provider in providers.items():
        if path[:len(prefix)] == prefix and len(path) == len(prefix) + 1:
            name, rg = opt("--name"), opt("--resource-group")
            if path[-1] == "show":
                rid = find(provider, name, rg) or missing()
                done(view(rid))
            if path[-1] == "list":
                done([view(rid) for rid, r in state["resources"].items() if r["provider"] == provider])
            if path[-1] == "create":
                assert rg in state["groups"], "created a resource outside an existing group"
                props = {}
                if provider.endswith("storageAccounts"):
                    props = {"isHnsEnabled": opt("--hns") == "true"}
                if provider.endswith("workspaces"):
                    props = {"workspaceUrl": f"adb-{len(state['resources'])}.azuredatabricks.net", "sku": {"name": opt("--sku")}}
                if provider.endswith("accessConnectors"):
                    props = {"identity": {"principalId": str(uuid.uuid4())}}
                create(provider, name, rg, props)
    if path[:2] == ("storage", "container-rm"):
        parent, name = opt("--storage-account"), opt("--name")
        rid = f"{parent}/blobServices/default/containers/{name}"
        if path[2] == "show":
            done(view(rid)) if rid in state["resources"] else missing()
        if path[2] == "create":
            assert parent in state["resources"], "container created on a missing account"
            state["resources"][rid] = {"provider": "containers", "name": name, "rg": state["resources"][parent]["rg"], "tags": {}}
            done(view(rid))
    if path[:2] == ("role", "assignment"):
        if path[2] == "list":
            done([view(rid) for rid, r in state["resources"].items() if r["provider"] == "roleAssignments"
                  and r["props"]["principal"] == opt("--assignee") and r["props"]["scope"] == opt("--scope")])
        if path[2] == "create":
            rid = f"{opt('--scope')}/providers/Microsoft.Authorization/roleAssignments/{uuid.uuid4()}"
            state["resources"][rid] = {"provider": "roleAssignments", "name": rid, "rg": None, "tags": {},
                                       "props": {"principal": opt("--assignee-object-id"), "scope": opt("--scope")}}
            done(view(rid))
        if path[2] == "delete":
            state["resources"].pop(opt("--ids"))
            done()
    if path[0] == "resource":
        if path[1] == "show":
            done(view(opt("--ids"))) if opt("--ids") in state["resources"] else missing()
        if path[1] == "delete":
            state["resources"].pop(opt("--ids"))
            done()
        if path[1] == "list":
            done([view(rid) for rid, r in state["resources"].items() if r["rg"] == opt("--resource-group")])
    raise SystemExit(f"unhandled az {argv}")

def databricks():
    noun, verb, args = positional[0], positional[1], positional[2:]
    kinds = {"storage-credentials": "storage_credential", "external-locations": "external_location", "catalogs": "catalog",
             "schemas": "schema", "volumes": "volume", "warehouses": "warehouse", "tables": "table", "functions": "function"}
    if (noun, verb) == ("metastores", "current"):
        done({"metastore_id": state["metastore"]}) if state["metastore"] else missing()
    if (noun, verb) == ("groups", "list"):
        done([{"displayName": group} for group in state["account_groups"]])
    objects = state["uc"].setdefault(kinds[noun], {})
    if verb in ("get", "read"):
        done(objects[args[0]]) if args[0] in objects else missing()
    if verb == "list":
        done(list(objects.values()))
    if verb == "delete":
        key = args[0]
        if key not in objects:
            missing()
        children = [name for kind in ("schema", "volume", "table", "function") for name in state["uc"].get(kind, {})
                    if name.startswith(key + ".")]
        if noun in ("catalogs", "schemas") and children:
            print("not empty", file=sys.stderr)
            sys.exit(1)
        del objects[key]
        done()
    if verb == "create":
        body = json.loads(opt("--json")) if opt("--json") else {}
        if noun == "schemas":
            key = f"{args[1]}.{args[0]}"
        elif noun == "volumes":
            key = ".".join(args[:3])
        elif noun == "warehouses":
            key = str(uuid.uuid4())
        else:
            key = args[0] if args else body["name"]
        objects[key] = {"id": key if noun == "warehouses" else str(uuid.uuid4()), "name": body.get("name", key),
                        "full_name": key, "comment": opt("--comment") or body.get("comment"), "body": body}
        if noun == "external-locations":
            objects[key]["url"] = args[1]
        done(objects[key])
    raise SystemExit(f"unhandled databricks {argv}")

azure() if tool == "az" else databricks()
'''


def initial_state():
    group = "/subscriptions/sub-1/resourceGroups/rg-shared/providers"
    return {
        "subscription": "sub-1",
        "groups": {"rg-shared": {"tags": {"owner": "platform"}}},
        "resources": {
            f"{group}/Microsoft.Databricks/workspaces/ws-shared": {
                "provider": "Microsoft.Databricks/workspaces", "name": "ws-shared", "rg": "rg-shared",
                "tags": {"owner": "platform"},
                "props": {"workspaceUrl": "adb-1.azuredatabricks.net", "sku": {"name": "premium"}},
            },
        },
        "metastore": "ms-1",
        "account_groups": ["sg-sovereignshield-admin", "sg-sovereignshield-researchers", "sg-sovereignshield-submitter-ca",
                           "sg-sovereignshield-submitter-us", "sg-sovereignshield-public"],
        "uc": {},
    }


@pytest.fixture
def estate(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "cli_stub.py"
    stub.write_text(STUB, encoding="utf-8")
    for tool in ("az", "databricks"):
        wrapper = bin_dir / tool
        wrapper.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "{stub}" {tool} "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    state, log, manifest_file = tmp_path / "state.json", tmp_path / "calls.jsonl", tmp_path / "manifest.json"
    state.write_text(json.dumps(initial_state()), encoding="utf-8")
    log.touch()
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "SS_STUB_STATE": str(state),
           "SS_STUB_LOG": str(log), "SOVEREIGN_RETRY_SECONDS": "0"}

    class Estate:
        manifest_path = manifest_file

        def run(self, script, *args, stdin=""):
            return subprocess.run(["bash", str(script), "--manifest", str(manifest_file), *args], env=env, input=stdin,
                                  capture_output=True, text=True, timeout=120)

        def up(self, *extra):
            return self.run(UP, "--subscription", "sub-1", "--resource-group", "rg-shared", "--workspace-name",
                            "ws-shared", "--key-vault", "kv-ss", "--storage-account", "stss", "--non-interactive",
                            "--skip-policies", *extra)

        def calls(self):
            return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

        def state(self):
            return json.loads(state.read_text(encoding="utf-8"))

        def manifest(self):
            return json.loads(manifest_file.read_text(encoding="utf-8"))

        def provenance(self):
            return {(item["kind"], item["name"]): item["pre_existing"] for item in self.manifest()["resources"]
                    if item.get("deleted_at") is None}

        def reset_log(self):
            log.write_text("", encoding="utf-8")

        def edit_state(self, change):
            current = self.state()
            change(current)
            state.write_text(json.dumps(current), encoding="utf-8")

    return Estate()


def creates(calls):
    return [call for call in calls if "create" in call]


def test_up_attaches_existing_estate_and_creates_only_the_delta(estate):
    result = estate.up("--yes")
    assert result.returncode == 0, result.stderr

    provenance = estate.provenance()
    for kind, name in (("resource_group", "rg-shared"), ("databricks_workspace", "ws-shared"), ("metastore", "ms-1")):
        assert provenance[(kind, name)] is True
    for kind, name in (("key_vault", "kv-ss"), ("storage_account", "stss"), ("access_connector", "dbac-sovereignshield"),
                       ("catalog", "dbw_sovereignshield"), ("schema", "dbw_sovereignshield.sovereign_shield"),
                       ("sql_warehouse", "sovereignshield-warehouse")):
        assert provenance[(kind, name)] is False

    created = creates(estate.calls())
    assert not [call for call in created if call[:3] in (["az", "group", "create"], ["az", "databricks", "workspace"])]
    for call in created:
        if call[0] == "az" and "--tags" in call:
            assert all(tag in call for tag in TAGS), call
    tagged = {tuple(call[1:3]) for call in created if "--tags" in call}
    assert {("keyvault", "create"), ("storage", "account"), ("databricks", "access-connector")} <= tagged
    uc_created = [" ".join(call) for call in created if call[0] == "databricks"]
    assert uc_created and all("ManagedBy" in call and "SovereignShield" in call for call in uc_created)
    assert estate.state()["groups"]["rg-shared"]["tags"] == {"owner": "platform"}, "attached group was re-tagged"


def test_rerun_creates_nothing_and_keeps_provenance(estate):
    assert estate.up("--yes").returncode == 0
    first = estate.provenance()
    estate.reset_log()

    assert estate.up("--yes").returncode == 0
    assert creates(estate.calls()) == []
    assert estate.provenance() == first


def test_dry_run_changes_nothing(estate):
    result = estate.up("--dry-run")

    assert result.returncode == 0, result.stderr
    assert creates(estate.calls()) == []
    assert "create  key_vault kv-ss" in result.stderr
    assert not estate.manifest_path.exists()


def test_up_refuses_to_create_without_confirmation(estate):
    result = estate.up()

    assert result.returncode != 0 and "--yes" in result.stderr
    assert creates(estate.calls()) == []


def test_down_removes_only_created_assets_in_dependency_order(estate):
    assert estate.up("--yes").returncode == 0
    estate.reset_log()

    result = estate.run(DOWN, "--yes")
    assert result.returncode == 0, result.stderr

    deletes = [" ".join(call[:3]) for call in estate.calls() if "delete" in call]
    order = [next(i for i, call in enumerate(deletes) if call.startswith(prefix)) for prefix in (
        "databricks volumes", "databricks schemas", "databricks catalogs", "databricks external-locations",
        "databricks storage-credentials", "databricks warehouses", "az role assignment",
    )]
    assert order == sorted(order)
    state = estate.state()
    assert "rg-shared" in state["groups"]
    assert any(r["name"] == "ws-shared" for r in state["resources"].values())
    assert not any(r["name"] in ("kv-ss", "stss", "dbac-sovereignshield") for r in state["resources"].values())
    assert state["uc"]["catalog"] == {} and state["metastore"] == "ms-1"
    remaining = estate.provenance()
    assert remaining and all(remaining.values()), "only attached resources remain active in the manifest"


def test_down_requires_typed_confirmation(estate):
    assert estate.up("--yes").returncode == 0
    estate.reset_log()

    result = estate.run(DOWN, stdin="DELETE\n")

    assert result.returncode != 0
    assert not [call for call in estate.calls() if "delete" in call]


def test_down_keeps_resources_whose_ownership_tag_changed(estate):
    assert estate.up("--yes").returncode == 0

    def adopt_vault(state):
        vault = next(r for r in state["resources"].values() if r["name"] == "kv-ss")
        vault["tags"] = {"owner": "another-team"}

    estate.edit_state(adopt_vault)
    result = estate.run(DOWN, "--yes")

    assert result.returncode == 2
    assert "kept key_vault kv-ss" in result.stderr
    assert any(r["name"] == "kv-ss" for r in estate.state()["resources"].values())
    assert estate.provenance()[("key_vault", "kv-ss")] is False


def test_down_dry_run_lists_plan_without_deleting(estate):
    assert estate.up("--yes").returncode == 0
    estate.reset_log()

    result = estate.run(DOWN, "--dry-run")

    assert result.returncode == 0
    assert "DELETE  key_vault kv-ss" in result.stderr and "KEEP    resource_group rg-shared" in result.stderr
    assert not [call for call in estate.calls() if "delete" in call]


def test_warehouse_policy_executor_records_what_it_created(tmp_path, monkeypatch):
    """The policy plane runs the shared executor and labels only new objects as created."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("apply_policies", ROOT / "scripts" / "apply_policies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    catalog = {("function", "sovereign_shield", "fn_old"), ("table", "sovereign_shield", "agg_sdmx_history")}

    class Cursor:
        description = None

        def execute(self, statement, parameters=None):
            self.rows = []
            self.description = None
            if "information_schema.routines" in statement:
                self.rows = [(schema, name) for kind, schema, name in catalog if kind == "function"]
            elif "information_schema.tables" in statement:
                self.rows = [(schema, name, "VIEW" if kind == "view" else "MANAGED") for kind, schema, name in catalog
                             if kind in ("table", "view")]
            self.description = [("column",)] if self.rows or "information_schema" in statement else None

        def fetchall(self):
            return self.rows

    class Connection:
        def cursor(self):
            return Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def apply_layer(spark):
        assert spark.sql("SELECT 1 FROM dbw_sovereignshield.information_schema.routines").collect() is not None
        catalog.update({("function", "sovereign_shield", "fn_new"), ("view", "sovereign_shield", "v_agg_sdmx_published")})

    monkeypatch.setattr(module, "connect", lambda host, warehouse: Connection())
    monkeypatch.setattr(module.apply_security, "apply_security_layer", apply_layer)
    monkeypatch.delenv("SOVEREIGNSHIELD_SKIP_GRANTS", raising=False)
    result = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["apply_policies.py", "--host", "https://adb-1.azuredatabricks.net/",
                                      "--warehouse-id", "wh", "--result", str(result), "--skip-grants"])
    module.main()

    recorded = {item["name"]: item["pre_existing"] for item in json.loads(result.read_text(encoding="utf-8"))}
    assert recorded == {
        "dbw_sovereignshield.sovereign_shield.fn_old": True,
        "dbw_sovereignshield.sovereign_shield.agg_sdmx_history": True,
        "dbw_sovereignshield.sovereign_shield.fn_new": False,
        "dbw_sovereignshield.sovereign_shield.v_agg_sdmx_published": False,
    }
    assert os.environ["SOVEREIGNSHIELD_SKIP_GRANTS"] == "1"
