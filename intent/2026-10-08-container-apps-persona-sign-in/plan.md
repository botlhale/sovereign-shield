# Plan: Restore persona sign-in on the Container Apps portal

- **Spec:** [spec.md](spec.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-08
- **Accepted by:** @botlhale, 2026-10-08 (request to fix and commit)

## Files that change

| File | Change |
| --- | --- |
| `sh/container_apps_deploy.ps1` | List-syntax login parameter with read-back; guarded permission; Graph consent |
| `sh/sovereignshield_up.ps1` | Stage 8 sign-in redirect check |
| `src/templates/portal.html` | Refresh-and-retry, `offerSignOut()` |
| `src/app.yaml` | Empty sign-out URL for the Databricks App |
| `src/api_gateway.py` | Audience in the refused-token log |
| `tests/test_deployment_boundaries.py`, `tests/test_api_gateway.py` | Regression tests |
| `evals/cases/easy-auth-scope-quoting.json`, `evals/README.md` | Eval case |
| `docs/AUTOMATION_RUNBOOK.md` | Recovery row; persona switching on each host |

## Order of work

1. Commit the failing tests on their own.
2. Turn fix mode on, implement R1 to R6 until the tests pass, turn it off and
   commit.
3. Correct the live login parameter, consent and permission list. Check the live
   redirect.
4. Redeploy with `-StartAtStage 3 -StopAfterStage 3`, then `-StartAtStage 5
   -StopAfterStage 8`.
5. Add the eval case and the runbook rows. Record the evidence.

## Risks

| Risk | Mitigation |
| --- | --- |
| The CLI parses the list syntax differently than expected | The script reads the value back and fails; the live change is checked the same way before redeploying |
| Replacing the Graph grant drops a scope someone relies on | The new grant is a superset of the existing `openid profile email` |
| Stage 6 reconciles the old snapshot instead of deploying | The run starts at Stage 5, so `--resume` is not passed |
| Existing sessions keep their Graph tokens | The owner signs out once; refused sessions now offer "Sign out" |

## Proof

```bash
.venv/bin/python -m pytest tests/ -p no:cacheprovider -o addopts=""
.venv/bin/python evals/run_evals.py --self-test
pwsh -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile(...)"  # both edited scripts
# live: sign-in redirect scope, then Stage 8 of the redeployment
```

## Rollback

Revert the commits listed by `git log --grep "Intent: 2026-10-08-container-apps-persona-sign-in"`
and redeploy Stages 3 and 5 to 8. The live parameter can be reset with the same
`az containerapp auth update --set` command.

## Evidence

Recorded on 8 October 2026. Status `implemented`: the owner's persona sign-in is
the last acceptance check.

- **Root cause.** The live sign-in redirect asked for `scope=openid profile email`
  and carried a separate `"scope=…` parameter. The workspace's SCIM `Me` endpoint
  answered HTTP 400 to a Microsoft Graph token and 200 to an Azure Databricks token
  for the same operator.
- **Tests.** The six tests from `064127d` failed there and pass at `25fa6d1`. Full
  offline suite: 396 passed, 14 skipped. The eval self-test reproduces 9 of 9
  incidents, including `easy-auth-scope-quoting`.
- **Live configuration.**
  - The login parameter now reads back as `scope=openid profile offline_access
    2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/user_impersonation`.
  - The live redirect requests that scope and nothing else.
  - The Microsoft Graph grant is `openid profile email offline_access` for all
    principals.
  - The app registration declares the Azure Databricks permission once instead of
    17 times.
- **Redeployment.**
  - Stage 3 succeeded on the fourth run. Three runs failed on workspace API
    requests that stalled for 90 seconds, and the first left a deploy lock, which
    was removed.
  - Stages 5 to 8 completed in 7 minutes 27 seconds:
    - Databricks App deployment `01f1c37f79fa12c889b2c9b821b56e00` succeeded;
    - Container App revision `ca-sovereignshield-portal--0000004` runs image
      `20261008211943`;
    - Stage 8 passed, including the new redirect check, with 13 public rows.
  - The live portal serves the fixed page, and anonymous `whoami` returns 200.
- **Outstanding.** The owner signs out at `/.auth/logout`, signs in as each persona
  on the Container Apps portal, and confirms that the entitled data appears.
