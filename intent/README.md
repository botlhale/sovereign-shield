# Intent Records

Every change to SovereignShield starts as a committed intent. Each change has one
folder, `intent/<YYYY-MM-DD>-<short-slug>/`, holding its artifact chain:

| Artifact | Stage | Answers | Approved by |
| --- | --- | --- | --- |
| `intent.md` | Plan | Which problem, for whom, and what outcome | Product owner |
| `spec.md` | Design | Requirements, design, flagged policy concerns, acceptance criteria | Product owner; policy owners for flagged concerns |
| `plan.md` | Build | Files, order, risks, proof, rollback and, once verified, evidence | Engineer who owns the change |

Commits that implement a change carry an `Intent: <folder>` trailer, so
`git log --grep "Intent: <folder>"` lists them. Pull request review findings and
those commits complete the record: the chain of commits is the audit trail.

Start a new record by copying [the templates](_template/).

## How to Request a Change

Describe the problem; the agent drafts each artifact; you approve each one before
the next starts. The prompts below work in Claude Code and in GitHub Copilot agent
mode, because both load [AGENTS.md](../AGENTS.md) and the skills in `.claude/skills/`.
The [operating model](../docs/AI_SDLC.md) explains the gates behind each step.

1. **Describe the problem, not the solution.** Say what is wrong, who notices and
   what evidence you have.

   > Use the intent-capture skill. Analysts cannot tell from the portal which of
   > two same-day filings is the accepted one; a submitter raised it after the
   > 6 October demo.

   The agent creates `intent/<date>-<slug>/intent.md` with status `draft`, adds it
   to the index and lists open questions. Answer them, correct the draft, set the
   status to `accepted` and commit it, or reject it.

2. **Specify.**

   > Use the spec-from-intent skill for intent/2026-10-07-accepted-filing-label.

   The agent writes `spec.md` with numbered requirements, testable acceptance
   criteria and *Flagged concerns* for anything a policy owner must decide. Resolve
   the concerns, then set the status to `specified`.

3. **Plan before any code.** In Claude Code press Shift+Tab for plan mode; in
   Copilot say that no files may change yet.

   > Plan intent/2026-10-07-accepted-filing-label with the implementation-plan
   > skill. Do not edit code yet.

   Review the files, order, risks, proof and rollback in `plan.md`, then set the
   status to `planned`.

4. **Build one step at a time.**

   > Implement step 1 of the plan. Run the verification block, show me the output
   > and commit with the Intent trailer.

   The agent commits locally with `Intent: <folder>` and `Assisted-by:` trailers.
   It stops and asks you before any cloud lifecycle command, `git push` or
   policy-file edit. Approve only if you own that gate. Before you call a step done,
   ask for an independent check:

   > Use the verifier subagent on this change.

5. **Review and merge.** Ask for the policy review, then push when you are ready.

   > Use the policy-reviewer subagent, then open a pull request that links the intent.

   The review workflow comments against [REVIEW.md](../REVIEW.md). Answer an
   Important finding yourself or comment `@claude fix the finding about ...`. A code
   owner approves the merge.

6. **Record the evidence.** After the merge, and after a reviewed cloud run when
   the change needs one:

   > Fill the Evidence section of the plan with the verification output and set the
   > intent to verified.

### Bugs: Failing Test First

> Use the intent-capture skill for this incident: down failed with
> ApplianceBeingDeleted on a rerun. Then write a regression test that fails today
> and commit it on its own.

Then lock the tests and ask for the fix:

```bash
touch .sovereignshield-fix-mode        # the gate now denies edits to tests/ and evals/
```

> Fix the incident in intent/2026-10-07-delete-rerun. Tests are locked; change the code.

Remove the marker once the suite is green (`rm .sovereignshield-fix-mode`; the
gate asks you to confirm), and add an eval case so agents keep the fix
([Adding a Case](../evals/README.md#adding-a-case)).

### Small Changes

A typo or a broken link still gets a record, but one request can draft all three
artifacts:

> Use intent-capture, spec-from-intent and implementation-plan in one pass for:
> the runbook links to a renamed heading. Keep each artifact to a few lines.

### Work Raised by Automation

- A full lifecycle run that falls outside its [control band](../ops/bands.yaml)
  drafts an intent here (`<date>-<up|down>-duration-change`). Triage it like any
  other draft: accept it, or reject it with the reason.
- The monthly security scan opens an `[intent candidate]` issue. Turn each finding
  you accept into an intent with the intent-capture skill.

## Status Lifecycle

`draft` → `accepted` → `specified` → `planned` → `implemented` → `verified`, or
`rejected` at any point. The status lives in `intent.md` and in the index below.

`retrospective` marks a record written after the change shipped. It is
reconstructed from the original request and the commits, and it does not claim
gate approvals that did not happen at the time.

## Index

| Intent | Status | Summary |
| --- | --- | --- |
| [2026-10-05-legacy-demo-history-migration](2026-10-05-legacy-demo-history-migration/intent.md) | retrospective | Never migrate local demo history without `--migrate-legacy` |
| [2026-10-05-linux-lifecycle](2026-10-05-linux-lifecycle/intent.md) | retrospective | Run the greenfield lifecycle from Linux with PowerShell 7 |
| [2026-10-06-lifecycle-timing-tables](2026-10-06-lifecycle-timing-tables/intent.md) | retrospective | Show how long each lifecycle step takes |
| [2026-10-06-teardown-bringup-hardening](2026-10-06-teardown-bringup-hardening/intent.md) | retrospective | Make teardown and rebuild finish without manual recovery |
| [2026-10-06-lifecycle-lock-before-azure-changes](2026-10-06-lifecycle-lock-before-azure-changes/intent.md) | retrospective | Lock before Stage 0 changes Azure; stop teardown on failed Azure CLI queries |
| [2026-10-06-reference-timings](2026-10-06-reference-timings/intent.md) | verified | Publish the 6 October lifecycle timings as the current reference |
| [2026-10-06-ai-native-sdlc](2026-10-06-ai-native-sdlc/intent.md) | verified | Run the repository on the six-stage AI-native SDLC |
| [2026-10-06-gemini-figure-review](2026-10-06-gemini-figure-review/intent.md) | verified | Decide whether the new Gemini engagement figures can be published |
| [2026-10-06-linux-provider-checksums](2026-10-06-linux-provider-checksums/intent.md) | verified | Lock the Terraform providers for Linux as well as Windows |
