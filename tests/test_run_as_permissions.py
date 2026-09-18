import importlib.util
from pathlib import Path

import pytest

from databricks.sdk.retries import retried
from databricks.sdk.service.iam import GrantRule

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_run_as", ROOT / "sh/configure_run_as.py")
configuration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configuration)


@pytest.fixture(autouse=True)
def verification_clock(monkeypatch):
    class RetryClock:
        elapsed = 0.0

        def time(self):
            return self.elapsed

        def sleep(self, seconds):
            self.elapsed += seconds

    clock = RetryClock()
    monkeypatch.setattr(configuration, "retried", lambda **kwargs: retried(clock=clock, **kwargs))
    return clock


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


def test_verification_recovers_delayed_visibility_without_rewriting(monkeypatch):
    from types import SimpleNamespace
    from databricks.sdk.service.iam import RuleSetResponse

    reads = []
    updates = []

    def get_rule_set(name, etag):
        reads.append(etag)
        rules = [] if len(reads) < 3 else [GrantRule(
            role=configuration.USE_ROLE, principals=["users/deployer@example.test"],
        )]
        return RuleSetResponse(name=name, etag=etag or "before", grant_rules=rules)

    def update_rule_set(name, rules):
        updates.append(rules)
        return RuleSetResponse(name=name, etag="after", grant_rules=rules.grant_rules)

    control = SimpleNamespace(get_rule_set=get_rule_set, update_rule_set=update_rule_set)
    monkeypatch.setattr(configuration, "AccountClient", lambda **kwargs: SimpleNamespace(access_control=control))
    monkeypatch.setattr(configuration, "WorkspaceClient", lambda **kwargs: SimpleNamespace(current_user=SimpleNamespace(me=lambda: SimpleNamespace(user_name="deployer@example.test"))))
    monkeypatch.setattr("sys.argv", ["configure_run_as.py", "--account-id", "account", "--client-id", "client", "--host", "https://example.test"])
    configuration.main()
    assert reads == ["", "after", "after"]
    assert len(updates) == 1


@pytest.mark.parametrize("rules", [
    [],
    [GrantRule(role="roles/servicePrincipal.manager", principals=["users/deployer@example.test"])],
    [GrantRule(role=configuration.USE_ROLE, principals=["users/other@example.test"])],
])
def test_verification_deadline_does_not_accept_missing_or_different_grants(rules, verification_clock):
    from unittest.mock import Mock, call
    from databricks.sdk.service.iam import RuleSetResponse

    control = Mock()
    control.get_rule_set.return_value = RuleSetResponse(name="runtime-rules", etag="after", grant_rules=rules)
    with pytest.raises(RuntimeError, match="within 120 seconds.*StartAtStage 3"):
        configuration.verify_user_role(control, "runtime-rules", "users/deployer@example.test", "after")
    assert verification_clock.elapsed >= 120
    assert control.get_rule_set.call_count > 1
    assert all(read == call(name="runtime-rules", etag="after") for read in control.get_rule_set.call_args_list)
    control.update_rule_set.assert_not_called()


def test_verification_does_not_retry_permission_denied():
    from unittest.mock import Mock
    from databricks.sdk.errors import PermissionDenied

    control = Mock()
    control.get_rule_set.side_effect = PermissionDenied("Account rule-set access denied")
    with pytest.raises(PermissionDenied, match="access denied"):
        configuration.verify_user_role(control, "runtime-rules", "users/deployer@example.test", "after")
    control.get_rule_set.assert_called_once_with(name="runtime-rules", etag="after")
    control.update_rule_set.assert_not_called()


def test_already_verified_role_never_rewrites_permissions(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock, call
    from databricks.sdk.service.iam import RuleSetResponse

    control = Mock()
    control.get_rule_set.return_value = RuleSetResponse(
        name="runtime-rules", etag="existing", grant_rules=[GrantRule(
            role=configuration.USE_ROLE, principals=["users/deployer@example.test"],
        )],
    )
    monkeypatch.setattr(configuration, "AccountClient", lambda **kwargs: SimpleNamespace(access_control=control))
    monkeypatch.setattr(configuration, "WorkspaceClient", lambda **kwargs: SimpleNamespace(current_user=SimpleNamespace(me=lambda: SimpleNamespace(user_name="deployer@example.test"))))
    monkeypatch.setattr("sys.argv", ["configure_run_as.py", "--account-id", "account", "--client-id", "client", "--host", "https://example.test"])
    configuration.main()
    name = "accounts/account/servicePrincipals/client/ruleSets/default"
    assert control.get_rule_set.call_args_list == [call(name=name, etag=""), call(name=name, etag="existing")]
    control.update_rule_set.assert_not_called()