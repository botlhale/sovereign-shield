# AI-Native SDLC Operating Model

SovereignShield is built with AI agents, Claude Code and GitHub Copilot, under the
six-stage [AI-native SDLC playbook](https://academy.claude.com/courses/ai-native-sdlc-playbook):
Plan, Design, Build, Test, Deploy and Maintain. Each stage commits an artifact that
the next stage reads, a named human approves at each gate, and deterministic
controls hold the gates that must not depend on an agent's judgement. The chain of
commits is the audit trail: `git log --grep "Intent: <folder>"` lists every commit
of one change, from its intent to its evidence.

To ask for a change, follow [How to Request a Change](../intent/README.md#how-to-request-a-change).

## Stages, Artifacts and Gates

| Stage | Artifact | Produced with | Human gate | Deterministic control |
| --- | --- | --- | --- | --- |
| Plan | `intent/<date>-<slug>/intent.md` | `intent-capture` skill | Product owner accepts the intent | `tests/test_ai_sdlc.py` checks folder names, statuses, sections and the index |
| Design | `spec.md` in the same folder | `spec-from-intent` skill and the domain skills | Product owner approves; each flagged concern goes to its policy owner | The same test requires a spec from status `specified` onwards |
| Build | `plan.md`, then the code, tests and documents | Plan mode, `implementation-plan` skill, [AGENTS.md](../AGENTS.md) | Engineer accepts the plan; the gate asks before cloud, publishing and policy-file actions | [PreToolUse gate](../.claude/hooks/pretool_gate.py) in both agents |
| Test | Test output pasted into the change; eval results | Verification block, `verifier` subagent, failing test first | None beyond the evidence itself | Offline suite and Terraform checks in [promote.yml](../.github/workflows/promote.yml); fix mode locks `tests/` and `evals/`; [agent evals](../evals/README.md) |
| Deploy | Pull request with review findings, then a reviewed cloud run | [REVIEW.md](../REVIEW.md), `policy-reviewer` subagent, [claude-review](../.github/workflows/claude-review.yml) | Code owner approves the merge; production environment reviewers approve promotion | [CODEOWNERS](../.github/CODEOWNERS), branch protection, the `promote.yml` environment gate |
| Maintain | Timing records, control-band results, scan issues, new intents | [Control bands](../ops/bands.yaml), monthly security scan | Service owner triages each draft intent or issue | `sh/check_lifecycle_bands.py` computes the bands; recording never fails a run |

Statuses move `draft` → `accepted` → `specified` → `planned` → `implemented` →
`verified`. A change is `verified` only when the Evidence section of its plan
holds the command output that proves the acceptance criteria. Records written after
the fact are marked `retrospective` and claim no gate approval that did not happen.

## Tiered Autonomy

| Tier | What the agent may do | Examples |
| --- | --- | --- |
| Act | Read, search, edit unprotected files, run offline checks, commit locally | Tests, documentation, `verify_docs.py`, `terraform validate` |
| Ask | Propose the action; a person approves it in the session | Up and down scripts, `terraform apply` or `destroy`, Azure deletes, bundle deploy, policy-file edits, `git push`, `gh pr merge` |
| Deny | Never, whatever the prompt says | Reading `.env` files, Terraform state or private keys; editing `tests/` or `evals/` in fix mode |
| Human only | Outside any agent's reach | Merging to `main`, approving production promotion, repository secrets and branch protection |

Agents write to `main` only through reviewed pull requests. The `@claude` responder
in the review workflow pushes only to the pull request's own branch.

## Sources of Truth

| Information | Source of truth | Where it is used |
| --- | --- | --- |
| Request, requirements, plan and evidence of one change | `intent/<folder>/` | Pull request description, commit trailers |
| Data, policy and delivery contracts | [Reference notes](../.github/skills/SKILLS.md) | Wrapped, not copied, by the skills in `.claude/skills/` |
| Agent instructions | [AGENTS.md](../AGENTS.md) | Imported by [CLAUDE.md](../CLAUDE.md); read directly by Copilot |
| Review criteria | [REVIEW.md](../REVIEW.md) | Review workflow, `policy-reviewer` subagent, human reviewers |
| Measured results | [Release evidence](RELEASE_EVIDENCE.md) | README, Executive Brief, White Paper and guides cite it |
| Lifecycle durations | [Timing history](../ops/lifecycle_timings.jsonl) | Control bands, the evidence register |
| Incidents | [Eval cases](../evals/README.md#cases) and their regression tests | Agent evals in CI |
| Review findings | The pull request | Fix commits that answer them |

## Roles

| Role | Decides | Holder |
| --- | --- | --- |
| Product owner | Accepts intents and approves specs | @botlhale |
| Policy owner | Unity Catalog policy, persona and SDMx contract concerns; the policy files | @botlhale |
| Engineer | Accepts plans, owns fix mode, approves gated agent actions | @botlhale |
| Code owner | Approves merges to `main` | @botlhale |
| Release and service owner | Approves production promotion and cloud runs; triages control-band and scan findings | @botlhale |

One person holds every role in this reference project. The gates therefore record
each decision but do not separate duties. An adopting organization assigns distinct
people, at least separating the policy owner and the release approver from the
engineer, and enables `prevent_self_review` on its production environment, which
`promote.yml` already verifies.

## Claude Code and GitHub Copilot

| Capability | Claude Code | GitHub Copilot in VS Code |
| --- | --- | --- |
| Project instructions | `CLAUDE.md`, which imports `AGENTS.md` | `AGENTS.md` |
| Skills | `.claude/skills/<name>/SKILL.md` | The same folders; VS Code discovers `.claude/skills` |
| Subagents | `.claude/agents/verifier.md`, `policy-reviewer.md` | The same files, offered as custom agents |
| Plan first | Plan mode (Shift+Tab) | Ask for the plan with the `implementation-plan` skill before any edit |
| Gate | `.claude/settings.json` runs `pretool_gate.py` | [.github/hooks/sovereignshield.json](../.github/hooks/sovereignshield.json) runs the same script |
| Credential reads | Permission deny rules and the gate | The gate |
| Pull request review | claude-review workflow | The same workflow reviews every pull request |
| Agent evals | `claude -p` in agent-evals | Not covered; the cases are agent-neutral and can be run with another CLI |

Hooks steer agents; they are not a security boundary. VS Code runs them only in a
trusted workspace with `chat.useHooks` on, and a user can disable them. Branch
protection, code owners and the production environment reviewers are the
enforcing controls.

## Deterministic and Advisory Controls

| Deterministic: holds regardless of the agent | Advisory: guides the agent and the reviewer |
| --- | --- |
| Offline test suite, including the structure of this process (`tests/test_ai_sdlc.py`) | `AGENTS.md` and `CLAUDE.md` instructions |
| Terraform format and validation, documentation link checks | Skills and their checklists |
| Pinned actions, least-privilege workflow permissions | `verifier` and `policy-reviewer` subagents |
| Branch protection and code-owner review, once enabled | AI review findings |
| Production environment reviewers in `promote.yml` | Agent eval pass rate, a signal about the instructions |
| The PreToolUse gate, while hooks are enabled | Draft intents written by the control bands or the scan |
| Control-band arithmetic in `sh/check_lifecycle_bands.py` | |

## Metrics

| Stage | Measure | Source |
| --- | --- | --- |
| Plan and Design | Time from committed intent to spec and to plan | `python sh/sdlc_metrics.py` |
| Build | Time from intent to last implementing commit; share of commits with an `Intent:` trailer | `python sh/sdlc_metrics.py` |
| Test | Offline suite result; eval self-test; agent pass rate against the 80% threshold | CI, `python evals/run_evals.py` |
| Deploy | Important review findings per pull request; time to merge | Pull requests |
| Maintain | Up and down durations against their bands; draft intents opened and closed | `python sh/check_lifecycle_bands.py`, `intent/README.md` |

The bands classify a run once five earlier complete runs exist. Until then the
check reports that the baseline is being built.

## Rollback

Every plan names its rollback. Code changes roll back with `git revert` of the
commits that carry the change's `Intent:` trailer, newest first. The environment
rolls back by rebuilding from code: the 6 October 2026 cycle tore the workload down
and brought it back up with the same scripts, which rehearses that path. Data and
policy changes follow the [migration gate](RELEASE_EVIDENCE.md#mandatory-migration-gate);
nothing destructive is implicit.

## One-Time Repository Setup

These steps need a repository administrator and are not automated:

1. Add the `ANTHROPIC_API_KEY` repository secret and install the Claude GitHub App
   on the repository. Until then the review, scan and agent-eval jobs write a skip
   notice and succeed.
2. Protect `main` with a ruleset: require a pull request, a code-owner review and
   the `Offline verification` and `Eval cases reproduce their incidents` checks,
   and block force pushes.
3. In VS Code, trust the workspace and keep `chat.useHooks` on, so the gate runs
   in Copilot sessions.
4. For regulated adoption, deploy the gate and permission rules as managed
   settings, so a project file cannot weaken them.
