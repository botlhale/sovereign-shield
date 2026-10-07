# Spec: Run the repository on the six-stage AI-native SDLC

- **Intent:** [intent.md](intent.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Approved by:** @botlhale, 2026-10-06
- **Skills applied:** none yet; this change creates them. The existing reference
  notes in `.github/skills/` and the repository security rules in CONTRIBUTING were
  applied directly.

## Requirements

### Plan

- **R1.** An intent home (`intent/`) with templates, a status lifecycle and an index.
  Every change has a dated folder, and implementing commits carry an
  `Intent: <folder>` trailer.

### Design

- **R2.** Each intent gains a `spec.md`, drafted with the policy skills. Concerns
  the skills cannot resolve are listed under *Flagged concerns*, each with the
  policy owner who decides it.

### Build

- **R3.** Each intent gains a `plan.md` (files, order, risks, proof, rollback),
  produced in plan mode and kept in sync with the code.
- **R4.** `AGENTS.md` holds the canonical project instructions for every agent:
  commands, a verification block, conventions, architecture, the SDLC flow and
  "things agents get wrong". `CLAUDE.md` imports it, adds Claude-specific notes and
  stays under one page.
- **R5.** Agent skills live at `.claude/skills/<name>/SKILL.md`, a location that
  both Claude Code and VS Code discover. Workflow skills cover intent capture, spec
  drafting and planning. Domain skills cover Unity Catalog policy, submission
  history, the SDMx contract, evidence and claims, and the cloud lifecycle. Domain
  skills point to the `.github/skills/` reference notes and do not copy them.
- **R6.** Subagents: a `verifier` that runs checks and never edits, and a
  `policy-reviewer` that applies REVIEW.md to a diff.
- **R7.** One PreToolUse gate script serves Claude Code (`.claude/settings.json`)
  and VS Code agent sessions (`.github/hooks/`). It:
  - asks for a human decision before cloud lifecycle commands (up and down scripts,
    `terraform apply/destroy/import/state rm`, Azure deletes, bundle
    deploy/destroy/run);
  - asks before publishing commands (`git push`, `gh pr merge`, `gh release`,
    `gh workflow run`);
  - asks before edits to the Unity Catalog policy files;
  - in fix mode, denies edits to `tests/` and `evals/`;
  - denies reads of credential files (`.env*`, Terraform state, private keys).

### Test

- **R8.** Single-command checks and a verification block are documented. The
  failing-test-first rule for bugs is enforced by fix mode.
- **R9.** Agent evals are derived from this session's incidents. Each case:
  - starts the agent from the defect;
  - scores the result deterministically (named pytest checks, plus a list of
    paths the agent must not change).

  A harness self-test proves each case reproduces its defect. CI runs the
  self-test on changes to agent configuration and weekly. When the API key is
  present, CI also runs the agent against the cases with a pass-rate threshold.
- **R10.** Each incident from this session has a regression test.

### Deploy

- **R11.** `REVIEW.md` defines four passes (bugs; security and data; compliance
  with intent, spec and plan; evidence and claims), the Important and Nit
  severities, a cap of five nits and a do-not-report list.
- **R12.** A `claude-review` workflow reviews pull requests against REVIEW.md and
  answers `@claude` requests on pull requests. It is pinned by SHA, uses minimal
  permissions, skips fork pull requests, and writes a skip notice when the API key
  is absent.
- **R13.** `CODEOWNERS` names the owner of every path, with the policy files and
  agent configuration listed explicitly. The pull request template asks for the
  intent folder and AI disclosure.
- **R14.** Tiered autonomy and the rehearsed rollback are documented.
  `promote.yml` remains the production gate.

### Maintain

- **R15.** Every full greenfield up run and every workload down run appends a
  timing record to `ops/lifecycle_timings.jsonl`. Recording never fails the
  lifecycle.
- **R16.** Deterministic control bands (`ops/bands.yaml`) classify the latest run
  as log, diagnose or propose. A propose result can write a draft intent.
- **R17.** A scheduled security scan, inert without the key, files at most one
  issue labelled as an intent candidate.
- **R18.** A process-metrics script reports lead times per intent and the share of
  recent commits that carry an `Intent:` trailer.

### Documentation and verification

- **R19.** `docs/AI_SDLC.md` describes the operating model:
  - stages, artifacts, gates and controls;
  - the source of truth for each artifact;
  - roles, and the single-owner limitation;
  - parity between Claude Code and Copilot;
  - which controls are deterministic and which are advisory;
  - metrics.

  The intent README teaches how to request a change. The README and CONTRIBUTING
  link to both, and the CONTRIBUTING anchor
  `ai-assisted-software-development-life-cycle` is kept.
- **R20.** Offline tests verify all of the above in CI.

## Design

| Concern | Location |
| --- | --- |
| Artifact chain | `intent/<date>-<slug>/{intent,spec,plan}.md`, `intent/README.md` index, `intent/_template/` |
| Agent context | `AGENTS.md` (canonical), `CLAUDE.md` (`@AGENTS.md` import plus Claude notes) |
| Skills and subagents | `.claude/skills/*/SKILL.md`, `.claude/agents/*.md` |
| Gates | `.claude/hooks/pretool_gate.py`, `.claude/settings.json`, `.github/hooks/sovereignshield.json`, fix-mode marker `.sovereignshield-fix-mode` or `SOVEREIGNSHIELD_FIX_MODE=1` |
| Review | `REVIEW.md`, `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/workflows/claude-review.yml` |
| Evals | `evals/run_evals.py`, `evals/cases/*.json`, `.github/workflows/agent-evals.yml` |
| Maintain | `ops/lifecycle_timings.jsonl`, `ops/bands.yaml`, `sh/check_lifecycle_bands.py`, `Add-SovereignShieldTimingRecord` in the orchestration module, `sh/sdlc_metrics.py` |
| Explanation | `docs/AI_SDLC.md`, README, CONTRIBUTING |

### Gate script

- **Input.** It reads both payload shapes: Claude Code (`Bash`, `Edit`, `Write`,
  `MultiEdit`, `NotebookEdit`, `Read`) and VS Code (`run_in_terminal`,
  `send_to_terminal`, `create_file`, `replace_string_in_file`,
  `multi_replace_string_in_file`, `edit_notebook_file`, `apply_patch`,
  `read_file`).
- **Output.** It returns the `hookSpecificOutput.permissionDecision` both
  harnesses accept.
- **Repository root.** It resolves the root from its own location.
- **Failure.** An unexpected error exits 1, a non-blocking warning, so a defect in
  the gate never stops all tool use.

### Eval case defects

Each defect is recorded as exact find-and-replace pairs, not context patches, so
an unrelated edit does not invalidate the case. The self-test requires each find
string to occur exactly once.

### Control bands

- **Baseline.** The previous runs of the same lifecycle with outcome `complete`:
  the last 10, and at least 5.
- **Rules, most severe first:**
  - one point beyond 3σ, or two of the last three beyond 2σ on the same side →
    propose;
  - eight consecutive points on one side of the mean, or one point beyond 2σ →
    diagnose;
  - beyond 1σ → log.
- **Floor.** σ is at least one minute, so a quiet baseline does not flag noise.

## Flagged concerns

| Concern | Policy owner | Resolution |
| --- | --- | --- |
| One person holds every role, so the gates record decisions but do not separate duties | @botlhale | Accepted for a reference project and stated in `docs/AI_SDLC.md`. A client adoption names distinct owners |
| AI review on a public repository can see prompt-injection text in pull requests | @botlhale (security) | The review job can only read code and comment. Fork pull requests are skipped. The action answers `@claude` only for users with write access |
| Hooks guide agents but are not a security boundary: VS Code ignores matchers, and a user can disable hooks | @botlhale | Branch protection, CODEOWNERS and the production environment reviewers remain the enforcing controls |
| Agent evals and scans spend API credits | @botlhale | They run on agent-configuration changes, weekly or monthly, and on demand. Without the key they are skipped |
| Timing records in a tracked file create diffs after each run | @botlhale | Only full runs are recorded. The operator commits them as evidence |

## Acceptance criteria

| Requirement | Proof |
| --- | --- |
| R1, R2, R3 | `tests/test_ai_sdlc.py` validates folder names, statuses, the sections each status requires, and the index |
| R4, R5, R6 | `tests/test_ai_sdlc.py` validates `CLAUDE.md` length and import, skill frontmatter and names, and the subagents |
| R7, R8 | `tests/test_ai_sdlc.py` feeds both payload shapes to the gate script and checks each decision |
| R9, R10 | `python evals/run_evals.py --self-test` passes. `tests/test_agent_evals.py` validates the case schema. New tests in `tests/test_deployment_boundaries.py` cover every incident |
| R11 to R14 | `tests/test_ai_sdlc.py` checks the review file, code owners, template, workflow pinning, permissions, triggers and key guards |
| R15, R16 | `tests/test_lifecycle_bands.py` covers each rule, the draft intent and the PowerShell record writer (when `pwsh` exists) |
| R17, R18 | Workflow checks above. `tests/test_sdlc_metrics.py` runs the metrics script on a temporary repository |
| R19, R20 | `sh/verify_docs.py` link check and the full offline suite |

## Out of scope

- Enabling branch protection, adding the API key secret or installing the Claude
  GitHub App. These are manual repository-admin steps, listed in `docs/AI_SDLC.md`.
- Enterprise managed settings, which are documented as the adoption step for
  regulated clients.
- Hook formats for the Copilot cloud agent and the Copilot CLI.
- Converting the `.github/skills/` reference notes into skills. They stay the
  source of truth, wrapped by the new skills.
