# Review Instructions

These instructions apply to every pull request, whoever reviews it. The
`claude-review` workflow gives them to Claude, and the `policy-reviewer` subagent
applies them locally. Review findings are advisory. Merging still needs a code
owner's approval.

## Before You Start

Find the change's intent folder. Look for a link in the pull request or an
`Intent:` trailer in its commits. Read `intent.md`, `spec.md` and `plan.md` before
reading the diff.

A change without an intent record is an Important finding unless it only fixes a
typo or a broken link.

## Passes

Run four passes, in order, and report each separately.

### 1. Bugs

- Logic errors, and unhandled failure paths. In particular:
  - ignored native exit codes;
  - `az ... wait` treated as success without re-checking state;
  - polling without a deadline.
- Portability: Windows-only paths or `cmd.exe` without a platform check, and
  PowerShell that would not parse.
- Python errors, and tests that would pass without the code they claim to prove.

### 2. Security and Data

- Secrets, tokens, state, tfvars values or real institutional data in the diff.
- Weakened fail-closed controls. Restricted values must stay NULL, never zero, and
  a principal in no persona group must see zero rows.
- Edits to Unity Catalog policy files without the policy owner's recorded
  approval: `src/unity_catalog_triple_lock.sql`, `src/unity_catalog_grants.sql`,
  `src/apply_security.py`, `scripts/apply_policies.py`.
- Workflow changes:
  - actions not pinned to a commit SHA;
  - permissions broader than the job needs;
  - `pull_request_target`;
  - pull request text reaching a shell or a privileged prompt.

### 3. Compliance with Intent, Spec and Plan

- Every requirement and acceptance criterion in `spec.md` is addressed. Anything
  beyond the spec is scope creep: name it.
- `plan.md` is updated wherever the implementation departs from it. Its
  *Evidence* section supports the status.
- The contracts in `.github/skills/` still hold: SDMx key order, history columns,
  replay semantics and persona boundaries.

### 4. Evidence and Claims

- Numbers in documents match `docs/RELEASE_EVIDENCE.md`.
- Dated `docs/LIVE_DEPLOYMENT_*.md` records keep their figures.
- No SLA, price ceiling, certification or "guarantee" wording.
- A changed figure source comes with a re-rendered image and manifest entry.

## Severity

- **Important:** incorrect behaviour, a security or data-governance regression,
  a lifecycle run that would fail or leave resources behind, a claim that
  contradicts the evidence, or a missing intent record. Must be resolved before
  merge.
- **Nit:** naming, wording or style. Report at most five per review and drop the
  rest.

## Do Not Report

- Generated files: `docs/figures/**/*.png`, manifest digests (tests check them),
  `demo/sdmx/` outputs and `terraform/.terraform.lock.hcl`.
- Formatting that `terraform fmt` or the test suite already enforces.
- Issues outside the diff. Suggest an intent instead.
- Requests for docstrings or comments on unchanged code.

## Output

Post one summary comment:

- the verdict, either "No Important findings" or "N Important findings";
- the findings grouped by pass, each with `file:line`, why it matters and a
  suggested fix;
- the nits last.

Add inline comments only for Important findings.
