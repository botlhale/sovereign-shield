"""Bring-your-own-estate scripts: attach what exists, create only the delta, remove only that.

The scripts run unchanged against stub ``az`` and ``databricks`` executables that keep
a small in-memory estate, so the provenance and teardown rules are checked offline.
"""

import contextlib
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

failures = state.get("failures", {})
for depth in (2, 1, 0):
    if (key := " ".join([tool] + positional[:depth])) in failures:
        print(failures[key], file=sys.stderr)
        sys.exit(1)
if "delete" in positional and any(" ".join([tool] + positional).startswith(p) for p in state.get("lingering", [])):
    sys.exit(0)

def opt(name):
    return (options.get(name) or [None])[0]

def done(payload=None):
    state_path.write_text(json.dumps(state))
    if payload is not None:
        print(json.dumps(payload))
    sys.exit(0)

def missing(name=None, code="ResourceNotFound"):
    if tool == "databricks":
        print(f"Error: Resource '{name}' does not exist.", file=sys.stderr)
    else:
        print(f"ERROR: ({code}) The requested resource was not found.\nCode: {code}", file=sys.stderr)
    sys.exit(1)

def tags():
    return dict(item.split("=", 1) for item in options.get("--tags", []))

def metadata():
    return dict(item.split("=", 1) for item in options.get("--metadata", []))

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
            group = state["groups"].get(name) or missing(code="ResourceGroupNotFound")
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
            state["resources"][rid] = {"provider": "containers", "name": name, "rg": state["resources"][parent]["rg"], "tags": {},
                                       "props": {"properties": {"metadata": metadata()}}}
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
    if path == ("rest",):
        rid = opt("--url").split("?")[0]
        if rid not in state["resources"]:
            print('Not Found({"error":{"code":"RoleAssignmentNotFound","message":"The role assignment does not exist."}})',
                  file=sys.stderr)
            sys.exit(1)
        done(view(rid))
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
        done(objects[args[0]]) if args[0] in objects else missing(args[0])
    if verb == "list":
        done([item for item in objects.values() if item.get("state") != "DELETED"])
    if verb == "delete":
        key = args[0]
        if key not in objects:
            missing(key)
        children = [name for kind in ("schema", "volume", "table", "function") for name in state["uc"].get(kind, {})
                    if name.startswith(key + ".")]
        if noun in ("catalogs", "schemas") and children:
            print("not empty", file=sys.stderr)
            sys.exit(1)
        if noun == "warehouses":
            objects[key]["state"] = "DELETED"
            done()
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
    container = next(call for call in created if call[1:3] == ["storage", "container-rm"])
    assert "--metadata" in container and all(tag in container for tag in TAGS)
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


def test_up_aborts_when_a_lookup_fails_for_any_reason_but_absence(estate):
    """An expired login must not look like a missing vault and trigger a create."""
    estate.edit_state(lambda state: state.update(failures={"az keyvault show": "(AuthorizationFailed) token expired"}))
    result = estate.up("--yes")

    assert result.returncode != 0
    assert "could not tell whether this exists" in result.stderr and "AuthorizationFailed" in result.stderr
    assert creates(estate.calls()) == []
    assert not estate.manifest_path.exists()


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


@pytest.mark.parametrize("label, name, marker", [
    ("storage_account stss", "stss", lambda resource: resource["tags"]),
    ("storage_container stss/sovereignshield", "sovereignshield",
     lambda resource: resource["props"]["properties"]["metadata"]),
])
def test_down_deletes_nothing_while_a_created_resource_is_adopted(estate, label, name, marker):
    """Nothing is removed while an account tag or container metadata names another owner."""
    assert estate.up("--yes").returncode == 0
    before = estate.provenance()

    def owner(value):
        def change(state):
            marker(next(r for r in state["resources"].values() if r["name"] == name))["ManagedBy"] = value
        return change

    estate.edit_state(owner("another-team"))
    estate.reset_log()
    result = estate.run(DOWN, "--yes")

    assert result.returncode == 2
    assert "Nothing was deleted" in result.stderr and label in result.stderr
    assert "pre_existing" not in result.stderr
    assert not [call for call in estate.calls() if "delete" in call]
    assert estate.provenance() == before

    estate.edit_state(owner("SovereignShield"))
    assert estate.run(DOWN, "--yes").returncode == 0
    assert all(estate.provenance().values())


def test_down_never_records_a_deletion_it_could_not_confirm(estate):
    """A Databricks auth failure stops teardown before the storage beneath Unity Catalog."""
    assert estate.up("--yes").returncode == 0
    before = estate.provenance()
    estate.edit_state(lambda state: state.update(failures={"databricks": "Error: invalid access token (401)"}))
    estate.reset_log()

    result = estate.run(DOWN, "--yes")

    assert result.returncode == 2
    assert "Teardown stopped at volume" in result.stderr
    assert estate.provenance() == before
    assert not [call for call in estate.calls() if call[0] == "az" and "delete" in call]
    assert any(r["name"] == "stss" for r in estate.state()["resources"].values())

    estate.edit_state(lambda state: state.pop("failures"))
    assert estate.run(DOWN, "--yes").returncode == 0
    assert all(estate.provenance().values()), "a rerun completes the teardown"


@pytest.mark.parametrize("failures, stop", [
    ({"az resource show": "ERROR: (SubscriptionNotFound) The subscription 'sub-1' could not be found.\nCode: SubscriptionNotFound",
      "az group show": "ERROR: (SubscriptionNotFound) The subscription 'sub-1' could not be found.\nCode: SubscriptionNotFound",
      "az rest": 'Not Found({"error":{"code":"SubscriptionNotFound","message":"Subscription not found."}})'},
     "Nothing was deleted"),
    ({"az resource show": "ERROR: (TooManyRequests) Throttled; the endpoint was not found in time.\nCode: TooManyRequests"},
     "Nothing was deleted"),
    ({"databricks": "Error: Workspace adb-1.azuredatabricks.net not found; the metastore does not exist."},
     "Teardown stopped at volume"),
])
def test_down_treats_only_an_object_not_found_error_as_absence(estate, failures, stop):
    """Control-plane failures that merely mention 'not found' never close a manifest entry."""
    assert estate.up("--yes").returncode == 0
    before = estate.provenance()
    estate.edit_state(lambda state: state.update(failures=failures))
    estate.reset_log()

    result = estate.run(DOWN, "--yes")

    assert result.returncode == 2
    assert stop in result.stderr
    assert estate.provenance() == before
    assert not [call for call in estate.calls() if call[0] == "az" and "delete" in call]

    estate.edit_state(lambda state: state.pop("failures"))
    assert estate.run(DOWN, "--yes").returncode == 0
    assert all(estate.provenance().values())


def test_down_closes_an_entry_only_once_its_object_is_reported_missing(estate):
    """An acknowledged delete that has not taken effect stops teardown and keeps the entry."""
    assert estate.up("--yes").returncode == 0
    before = estate.provenance()
    estate.edit_state(lambda state: state.update(lingering=["databricks volumes delete"]))
    estate.reset_log()

    result = estate.run(DOWN, "--yes")

    assert result.returncode == 2
    assert "still reported present" in result.stderr and "Teardown stopped at volume" in result.stderr
    assert estate.provenance() == before
    assert not [call for call in estate.calls() if call[:3] == ["databricks", "schemas", "delete"]]

    estate.edit_state(lambda state: state.pop("lingering"))
    assert estate.run(DOWN, "--yes").returncode == 0
    assert all(estate.provenance().values())


def test_down_dry_run_lists_plan_without_deleting(estate):
    assert estate.up("--yes").returncode == 0
    estate.reset_log()

    result = estate.run(DOWN, "--dry-run")

    assert result.returncode == 0
    assert "DELETE  key_vault kv-ss" in result.stderr and "KEEP    resource_group rg-shared" in result.stderr
    assert not [call for call in estate.calls() if "delete" in call]


def policy_function(name):
    import apply_security

    statements = [statement for statement, _ in apply_security.parse_statements(
        (ROOT / "src" / "unity_catalog_triple_lock.sql").read_text(encoding="utf-8"))]
    return apply_security.version_policy_functions(statements)[1][name]


def warehouse_policy_executor(catalog, monkeypatch, applied=None, fails=False):
    """apply_policies.py over a fake warehouse whose information_schema lists ``catalog``."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("apply_policies", ROOT / "scripts" / "apply_policies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

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
        if applied is not None:
            applied.append(True)
        catalog.update({("function", "sovereign_shield", policy_function("fn_rls_multi_persona_lock")),
                        ("view", "sovereign_shield", "v_agg_sdmx_published"),
                        ("function", "sovereign_shield", "fn_other_team"), ("table", "sovereign_intake", "other_team")})
        if fails:
            raise RuntimeError("a later DDL statement failed")

    monkeypatch.setattr(module, "connect", lambda host, warehouse: Connection())
    monkeypatch.setattr(module.apply_security, "apply_security_layer", apply_layer)
    monkeypatch.delenv("SOVEREIGNSHIELD_SKIP_GRANTS", raising=False)
    return module


def run_policy_executor(module, result, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["apply_policies.py", "--host", "https://adb-1.azuredatabricks.net/",
                                      "--warehouse-id", "wh", "--result", str(result), "--skip-grants", *extra])
    module.main()


@pytest.mark.parametrize("fails", [False, True])
def test_warehouse_policy_executor_records_what_it_created(tmp_path, monkeypatch, fails):
    """The policy plane labels only new policy objects as created, also when a later statement fails.

    Objects another operator creates in the shared schemas meanwhile are not policy objects, so they are
    left out of the result instead of being claimed for teardown.
    """
    old = policy_function("fn_ddm_obs_conf_mask")
    catalog = {("function", "sovereign_shield", old), ("table", "sovereign_shield", "agg_sdmx_history"),
               ("function", "sovereign_shield", "fn_unrelated")}
    module = warehouse_policy_executor(catalog, monkeypatch, fails=fails)
    result = tmp_path / "result.json"
    with pytest.raises(RuntimeError) if fails else contextlib.nullcontext():
        run_policy_executor(module, result, monkeypatch, "--adopt-existing")

    recorded = {item["name"]: item["pre_existing"] for item in json.loads(result.read_text(encoding="utf-8"))}
    assert recorded == {
        f"dbw_sovereignshield.sovereign_shield.{old}": True,
        "dbw_sovereignshield.sovereign_shield.agg_sdmx_history": True,
        f"dbw_sovereignshield.sovereign_shield.{policy_function('fn_rls_multi_persona_lock')}": False,
        "dbw_sovereignshield.sovereign_shield.v_agg_sdmx_published": False,
    }
    assert os.environ["SOVEREIGNSHIELD_SKIP_GRANTS"] == "1"


@pytest.mark.parametrize("schema,name", [("sovereign_shield", "agg_sdmx_history"),
                                         ("sovereign_intake", "lbs_micro_transactions"),
                                         ("sovereign_shield", "v_agg_sdmx_published")])
def test_warehouse_policy_executor_refuses_to_modify_objects_it_did_not_create(tmp_path, monkeypatch, schema, name):
    """Rebinding or replacing an attached table or view is not reversible, so it needs explicit adoption."""
    applied = []
    module = warehouse_policy_executor({("table", schema, name)}, monkeypatch, applied)
    result = tmp_path / "result.json"

    with pytest.raises(SystemExit, match=f"dbw_sovereignshield.{schema}.{name}"):
        run_policy_executor(module, result, monkeypatch)

    assert not applied
    assert json.loads(result.read_text(encoding="utf-8")) == []


def test_warehouse_policy_executor_reapplies_objects_a_previous_run_created(tmp_path, monkeypatch):
    applied = []
    module = warehouse_policy_executor({("table", "sovereign_shield", "agg_sdmx_history")}, monkeypatch, applied)

    run_policy_executor(module, tmp_path / "result.json", monkeypatch,
                        "--owned", "dbw_sovereignshield.sovereign_shield.agg_sdmx_history")

    assert applied
