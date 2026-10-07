# AGENTS.md

Instructions for every coding agent working in this repository: Claude Code (through
`CLAUDE.md`), GitHub Copilot and others. SovereignShield is a synthetic-data
reference architecture for governed SDMx exchange on Azure Databricks: Python 3.12
in `src/`, PowerShell 7 and Python lifecycle tooling in `sh/`, Terraform in
`terraform/`, and a Databricks Asset Bundle in `databricks.yml`.

## How Work Flows

Every change follows the AI-native SDLC described in `docs/AI_SDLC.md`:
intent → spec → plan → implementation → pull request review → evidence.

- Start from `intent/<date>-<slug>/` (see the [intent records](intent/README.md)).
  Do not write code until `plan.md` is accepted. If there is no intent, draft one
  with the `intent-capture` skill and stop for approval.
- Keep `plan.md` in sync when the implementation departs from it.
- End commit messages with `Intent: <folder>` and `Assisted-by: <agent (model)>`.
- Bugs: write the failing test first and commit it, then fix in fix mode
  (`touch .sovereignshield-fix-mode`; remove it afterwards), which locks `tests/`
  and `evals/`. Fix the code, never the test.

## Commands

```bash
python -m pytest tests/ -p no:cacheprovider -o addopts=""   # offline suite, prints totals
python -m pytest tests/<file>.py -p no:cacheprovider -o addopts=""
python sh/verify_docs.py                                     # links and anchors (sh/requirements-docs.txt)
python sh/verify_docs.py --print-proof                       # after publication edits: brief must be 8 pages
python evals/run_evals.py --self-test                        # committed eval cases still reproduce their incidents
python sh/check_lifecycle_bands.py                           # latest lifecycle durations against ops/bands.yaml
python sh/sdlc_metrics.py                                    # intent lead times and Intent: trailer coverage
terraform -chdir=terraform fmt -recursive -check
terraform -chdir=terraform init -backend=false -input=false && terraform -chdir=terraform validate
```

Use the repository virtual environment (`.venv/bin/python` or `.venv\Scripts\python`).
PowerShell edits: parse every changed `.ps1` with
`[System.Management.Automation.Language.Parser]::ParseFile` before reporting done.

## Verification Block

Before saying a change is done, run the commands relevant to it, paste the result
lines (pass, fail and skip counts), and state anything you could not run. A claim
without output is not verified.

## Architecture

| Path | Contents |
| --- | --- |
| `src/` | Gateway (`api_gateway.py`, `uc_query.py`), validation (`sdmx_rule_validator.py`), history (`submission_history.py`, `spark_submission_history.py`), policy (`unity_catalog_triple_lock.sql`, `unity_catalog_grants.sql`, `apply_security.py`) |
| `sh/` | Greenfield lifecycle (`sovereignshield_up.ps1`, `sovereignshield_down.ps1`, `lib/SovereignShield.Orchestration.psm1`) and Python helpers |
| `scripts/` | Bring-your-own-estate bash lifecycle and policy application |
| `terraform/`, `databricks.yml` | Foundation infrastructure; data and policy plane |
| `.github/skills/` | Reference contracts, the source of truth for data, policy and delivery rules |
| `.claude/`, `REVIEW.md` | Agent skills, subagents and hooks; review criteria |
| `intent/` | Change records: intent, spec and plan per change |
| `evals/` | Agent evals: one case per past incident, scored by the regression tests |
| `ops/` | Lifecycle timing history (appended by full up and down runs) and its control bands |

## Skills

Load the matching skill from `.claude/skills/` before working in its area:
`intent-capture`, `spec-from-intent`, `implementation-plan` (workflow);
`unity-catalog-policy`, `submission-history`, `sdmx-contract`,
`evidence-and-claims`, `cloud-lifecycle` (domain).

## Rules

- Synthetic data only. Never put secrets, tokens, tfvars values, state or real
  institutional data in files, prompts or output.
- Controls fail closed. Policy files (`src/unity_catalog_triple_lock.sql`,
  `src/unity_catalog_grants.sql`, `src/apply_security.py`,
  `scripts/apply_policies.py`) change only with the policy owner's approval.
- Cloud lifecycle commands, `git push` and merges need a named human approval; the
  hooks ask for it. Never work around a hook.
- Measured results live in `docs/RELEASE_EVIDENCE.md`; dated records stay historical.

## Things Agents Get Wrong

Add to this list when the same mistake happens twice.

- Captured `az` output hides interactive prompts: install extensions explicitly
  (`Install-SovereignShieldAzExtension`) before first use.
- `az ... wait` exits 0 on timeout, and CLI polling can stop before Azure finishes:
  re-check the resource state, with a deadline, before continuing.
- Windows-only paths (`.venv\Scripts\python.exe`, `cmd.exe`) break Linux runs:
  use `Get-SovereignShieldPython` and branch on the platform.
- On Linux the lifecycle lock is an flock: never hold it while pytest runs.
- `.gitignore` matches `lib/`, so new files under `sh/lib/` need `git add -f`.
  Stage by path; a provider lock refreshed by a local `terraform init` is not part
  of an unrelated change.
- `sh/verify_docs.py --render-diagrams` re-renders every figure and rewrites the
  manifest. When one figure changes, render only that figure.
- Legacy history is never migrated or deleted implicitly (`--migrate-legacy`).
- Documentation tests forbid first-person authorship claims and some phrasings in
  Markdown; see `test_documentation_avoids_author_centric_architecture_claims`.
