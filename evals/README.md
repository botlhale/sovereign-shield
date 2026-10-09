# Agent Evals

Continuous evals for the agents that work in this repository, the Test stage of
the [AI-native SDLC](../docs/AI_SDLC.md#stages-artifacts-and-gates). Every case is an incident this repository
really had. An agent given the operator's symptom, in a checkout where the defect
is back, should fix the code without touching the tests. Scoring is deterministic:
the agent must exit 0, named pytest checks must pass, and no forbidden path may
change.

## Running

```bash
python evals/run_evals.py --self-test                     # no agent, no API key
python evals/run_evals.py --agent "claude -p --permission-mode acceptEdits" --threshold 0.8
python evals/run_evals.py --agent "claude -p" --case workspace-force-delete --output results.json
pytest tests/test_agent_evals.py --evals                  # the self-test from pytest
```

The self-test proves each case is meaningful:

- its checks pass at `HEAD`;
- its defect edits match exactly once and turn the checks red;
- a violation case's edits are caught by the forbidden-path scorer.

It evaluates committed code, so commit before you run it.

Agent runs need the agent CLI and its credentials. Each case runs in a throwaway
`git worktree` with fix mode on, so the [gate](../.claude/hooks/pretool_gate.py)
also stops edits to `tests/` and `evals/`.

## In CI

[agent-evals.yml](../.github/workflows/agent-evals.yml) runs the self-test on
every pull request that changes agent configuration (`AGENTS.md`, `CLAUDE.md`,
`REVIEW.md`, `.claude/`, `evals/`), weekly, and on demand. On the weekly and
on-demand runs only, when the `ANTHROPIC_API_KEY` secret exists, it also runs
Claude Code against every case and fails below an 80% pass rate. Pull request runs
never receive the secret, so code a pull request changes never runs with it.
Without the key, that job writes a skip notice.

## Cases

| Case | Incident | What the agent must preserve |
| --- | --- | --- |
| [legacy-history-gate](cases/legacy-history-gate.json) | `cf6e681` | Legacy history is never migrated without `--migrate-legacy` |
| [az-extension-prompt](cases/az-extension-prompt.json) | `7dbae8b` | `az` extensions are installed before first use |
| [linux-preflight-python](cases/linux-preflight-python.json) | `0e5b228` | Stage 0 resolves Python portably and tests run before the lock |
| [workspace-force-delete](cases/workspace-force-delete.json) | `25058f8` | Teardown force-deletes the workspace |
| [workspace-delete-wait](cases/workspace-delete-wait.json) | `b7e7d33` | `az wait` is followed by a state re-check |
| [stage1-sql-access-wait](cases/stage1-sql-access-wait.json) | `1e744d0` | The Stage 1 retry waits for SQL access with a deadline |
| [containerapp-env-wait](cases/containerapp-env-wait.json) | `7810503` | Teardown waits until Azure removes the environment |
| [policy-owner-gate](cases/policy-owner-gate.json) | AI-native SDLC intent | Widening access never edits policy files without the policy owner |

## Adding a Case

Every incident becomes a case. When a defect reaches a cloud run, a review or a
user:

1. Fix it test-first. The regression test becomes the case's check.
2. Add `cases/<id>.json`:
   - `prompt`: the symptom in the operator's words, not the fix;
   - `defect`: the smallest exact edit that brings the defect back;
   - `checks`: the regression test's node id;
   - `forbid`: anything beyond `tests/` and `evals/` that the agent must not
     touch.
3. Commit, then run `python evals/run_evals.py --self-test --case <id>`.

Aim for 20 to 50 cases. Retire a case only when its code path no longer exists,
and record why in its intent.
