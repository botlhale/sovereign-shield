"""Grant the authenticated deployer permission to bind the configured runtime identity."""

import argparse
from datetime import timedelta

from databricks.sdk import AccountClient, WorkspaceClient
from databricks.sdk.retries import retried
from databricks.sdk.service.iam import GrantRule, RuleSetUpdateRequest

USE_ROLE = "roles/servicePrincipal.user"


class _RoleNotVisible(RuntimeError):
    pass


def rules_with_user_role(rules, principal):
    updated = [GrantRule.from_dict(rule.as_dict()) for rule in rules]
    for rule in updated:
        if rule.role == USE_ROLE:
            if principal in (rule.principals or []):
                return updated, False
            rule.principals = list(rule.principals or []) + [principal]
            return updated, True
    updated.append(GrantRule(role=USE_ROLE, principals=[principal]))
    return updated, True


def verify_user_role(access_control, name, principal, etag, *, timeout=timedelta(minutes=2)):
    @retried(on=[_RoleNotVisible], timeout=timeout)
    def read_role():
        verified = access_control.get_rule_set(name=name, etag=etag)
        if any(rule.role == USE_ROLE and principal in (rule.principals or []) for rule in verified.grant_rules or []):
            return
        print("Waiting for the runtime identity use grant to become visible; permissions will not be rewritten.", flush=True)
        raise _RoleNotVisible("The runtime identity use role is not visible yet.")

    try:
        read_role()
    except TimeoutError as error:
        raise RuntimeError(
            f"The runtime identity use role was not verified within {timeout.total_seconds():g} seconds "
            f"for {principal} on {name}. Resume sovereignshield_up.ps1 with -StartAtStage 3 "
            "after checking the account grant; teardown is not required."
        ) from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--host", required=True)
    args = parser.parse_args()
    workspace = WorkspaceClient(host=args.host, auth_type="azure-cli")
    deployer = workspace.current_user.me()
    if not deployer.user_name:
        raise RuntimeError("The authenticated deployer has no user name.")
    principal = f"users/{deployer.user_name}"
    account = AccountClient(host="https://accounts.azuredatabricks.net", account_id=args.account_id, auth_type="azure-cli")
    name = f"accounts/{args.account_id}/servicePrincipals/{args.client_id}/ruleSets/default"
    current = account.access_control.get_rule_set(name=name, etag="")
    rules, changed = rules_with_user_role(current.grant_rules or [], principal)
    verification_etag = current.etag
    if changed:
        updated = account.access_control.update_rule_set(name, RuleSetUpdateRequest(name=name, etag=current.etag, grant_rules=rules))
        verification_etag = updated.etag
    verify_user_role(account.access_control, name, principal, verification_etag)
    print(f"Runtime identity use permission verified for {deployer.user_name}.")


if __name__ == "__main__":
    main()