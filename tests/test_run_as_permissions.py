import importlib.util
from pathlib import Path

from databricks.sdk.service.iam import GrantRule

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_run_as", ROOT / "sh/configure_run_as.py")
configuration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configuration)


def test_use_role_preserves_manager_and_other_users():
    original = [
        GrantRule(role="roles/servicePrincipal.manager", principals=["users/owner@example.test"]),
        GrantRule(role=configuration.USE_ROLE, principals=["users/existing@example.test"]),
    ]
    updated, changed = configuration.rules_with_user_role(original, "users/deployer@example.test")
    assert changed
    assert updated[0] == original[0]
    assert updated[1].principals == ["users/existing@example.test", "users/deployer@example.test"]
    assert original[1].principals == ["users/existing@example.test"]
    repeated, changed = configuration.rules_with_user_role(updated, "users/deployer@example.test")
    assert not changed
    assert repeated == updated


def test_verification_requires_the_updated_etag(monkeypatch):
    from types import SimpleNamespace
    from databricks.sdk.service.iam import RuleSetResponse

    reads = []

    def get_rule_set(name, etag):
        reads.append(etag)
        rules = [] if not etag else [GrantRule(role=configuration.USE_ROLE, principals=["users/deployer@example.test"])]
        return RuleSetResponse(name=name, etag=etag or "before", grant_rules=rules)

    control = SimpleNamespace(
        get_rule_set=get_rule_set,
        update_rule_set=lambda name, rules: RuleSetResponse(name=name, etag="after", grant_rules=rules.grant_rules),
    )
    monkeypatch.setattr(configuration, "AccountClient", lambda **kwargs: SimpleNamespace(access_control=control))
    monkeypatch.setattr(configuration, "WorkspaceClient", lambda **kwargs: SimpleNamespace(current_user=SimpleNamespace(me=lambda: SimpleNamespace(user_name="deployer@example.test"))))
    monkeypatch.setattr("sys.argv", ["configure_run_as.py", "--account-id", "account", "--client-id", "client", "--host", "https://example.test"])
    configuration.main()
    assert reads == ["", "after"]