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

Recorded when the status becomes verified.
