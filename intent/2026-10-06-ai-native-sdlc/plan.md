# Plan: Run the repository on the six-stage AI-native SDLC

- **Spec:** [spec.md](spec.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Accepted by:** @botlhale, 2026-10-06

## Files that change

| Step | Files |
| --- | --- |
| 1. Agent context and skills | `AGENTS.md`, `CLAUDE.md`, `.claude/skills/{intent-capture,spec-from-intent,implementation-plan,unity-catalog-policy,submission-history,sdmx-contract,evidence-and-claims,cloud-lifecycle}/SKILL.md`, `.claude/agents/{verifier,policy-reviewer}.md` |
| 2. Gates and review | `.claude/hooks/pretool_gate.py`, `.claude/settings.json`, `.github/hooks/sovereignshield.json`, `.gitignore`, `REVIEW.md`, `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/workflows/claude-review.yml`, `tests/test_ai_sdlc.py` |
| 3. Evals | `evals/README.md`, `evals/run_evals.py`, `evals/cases/*.json`, `.github/workflows/agent-evals.yml`, `tests/test_agent_evals.py`, `tests/conftest.py` (`--evals`), `pytest.ini` marker, new regression tests in `tests/test_deployment_boundaries.py` |
| 4. Maintain loop | `ops/lifecycle_timings.jsonl`, `ops/bands.yaml`, `sh/check_lifecycle_bands.py`, `sh/sdlc_metrics.py`, `sh/lib/SovereignShield.Orchestration.psm1` (`Add-SovereignShieldTimingRecord`), `sh/sovereignshield_up.ps1`, `sh/sovereignshield_down.ps1`, `docs/AUTOMATION_RUNBOOK.md` (timing record), `tests/test_lifecycle_bands.py`, `tests/test_sdlc_metrics.py`, `tests/test_deployment_boundaries.py` (module export guard) |
| 5. Explanation | `docs/AI_SDLC.md`, `intent/README.md` (How to Request a Change), `README.md`, `CONTRIBUTING.md`, `evals/README.md` links |

## Order of work

1. **Agent context and skills.** Advisory content first, so later steps can cite
   it.
2. **Gates.**
   - Write the gate script and its tests.
   - Run the tests against both payload shapes before adding the hook
     configuration, because the VS Code hook file applies to the session that
     creates it.
   - Then add the review file, code owners, template and review workflow.
3. **Evals.**
   - Write the regression tests for the incidents that lack one, and confirm each
     passes at the current code.
   - Write each case's defect and confirm with `--self-test` that it turns its
     checks red.
   - Add the workflow.
4. **Maintain loop.**
   - Write the band script and its tests.
   - Add the record writer to the orchestration module.
   - Call it from both lifecycle scripts only for full runs, inside `finally`, so
     it never masks the original error.
   - Export it from the module. The first test run caught the missing export,
     which would have thrown inside `finally` on the next cloud run; a guard test
     now checks every module function the scripts call is exported.
   - Document the record in the runbook in the same commit, since it changes what
     an operator commits after a run.
   - Seed the history with the operator-reported 6 October totals.
5. **Explanation.** Write the operating model, the request guide and the links,
   then run the full proof.

Each step is one commit with the trailer `Intent: 2026-10-06-ai-native-sdlc`.
Steps 1 and 2 landed as one commit, because `CLAUDE.md` and `AGENTS.md`
describe the gates and would otherwise point to controls that did not exist yet.
The subagents moved to that commit too, since they apply `REVIEW.md`.

## Risks

| Risk | Mitigation |
| --- | --- |
| A gate-script defect blocks every tool call in the editor | Unexpected errors exit 1, a non-blocking warning in both harnesses. Tests run before the hook file exists |
| A gate false positive (for example an `az` query containing "delete") | The decision is `ask`, not `deny`, so a human can approve it |
| A workflow YAML error is only found on GitHub | Tests parse every workflow and check its triggers, permissions, pins and key guards |
| An eval defect drifts as code changes | Find strings must match exactly once; the self-test fails loudly and names the case |
| A lifecycle script regression from the timing record | The writer catches its own errors and warns. It runs after the timing summary in `finally`. PowerShell parse check, plus a pwsh test when available |
| The secret scanner flags workflow references | Only `${{ secrets.NAME }}` references; no literals |
| A broken CONTRIBUTING anchor linked by the pull request template | The heading text stays unchanged; `verify_docs.py` checks the anchor |

## Proof

```bash
.venv/bin/python -m pytest tests/ -p no:cacheprovider -o addopts=""
.venv/bin/python -m pytest tests/test_agent_evals.py --evals -p no:cacheprovider -o addopts=""
.venv/bin/python evals/run_evals.py --self-test
.venv/bin/python sh/check_lifecycle_bands.py
.venv/bin/python sh/sdlc_metrics.py
.venv/bin/python sh/verify_docs.py
pwsh -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile(...)"  # each edited .ps1
```

## Rollback

Revert the commits listed by `git log --grep "Intent: 2026-10-06-ai-native-sdlc"`
in reverse order. The only runtime change is the timing record in the lifecycle
scripts, which is append-only and cannot fail a run.

## Evidence

Re-verified on 8 October 2026 at commit `b0c7178`, which adds the second round
of review fixes: the gate denies Terraform commands that read state, the review
job takes agent instructions from the base branch while respond skips pull
requests that change them, and draft intents are keyed by the flagged run. Run on
Ubuntu Linux with Python 3.12.

- Full offline suite: 384 passed, 13 skipped. The skips are the opt-in eval,
  live and stress tests.
- `pytest tests/test_agent_evals.py --evals`: 6 passed.
  `evals/run_evals.py --self-test`: 8 of 8 cases reproduce their incidents.
- `sh/check_lifecycle_bands.py` reports that both baselines are still being built
  (0 of 5 earlier complete runs). `sh/sdlc_metrics.py` reports `Intent:` trailer
  coverage of 17 of 23 non-merge commits since the intent home was created.
- `sh/verify_docs.py` verified 465 local Markdown links and heading anchors.
- Not run at this commit: `terraform fmt -check` (Terraform is not installed in
  this environment; no Terraform file changed). No PowerShell file changed.

Previously re-verified at commit `f4b7381`: 377 passed, 13 skipped; 6 eval tests
passed; 8 of 8 self-test cases; 465 links and anchors; the three edited
PowerShell files parsed without errors.

First verified on 6 October 2026 at commit `7436355` (Python 3.14): 347 passed,
14 skipped; 4 eval tests passed; 459 links and anchors; `terraform fmt -check`
clean.
- The gate has been active in the VS Code session that built this change since
  `351820c`, and no ungated tool call was blocked.

Not verified here: the review, scan and agent-eval jobs run on GitHub only after the
API key secret is added, and branch protection is a manual step. Both are listed in
`docs/AI_SDLC.md` under One-Time Repository Setup.
