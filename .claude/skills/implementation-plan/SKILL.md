---
name: implementation-plan
description: Turn an approved spec.md into plan.md (files, order, risks, proof, rollback) before any code is edited, then keep it in sync during the build and record the evidence. Use when a spec is approved, when implementation departs from the plan, or when a change is ready to be marked verified.
---

# Implementation Plan

Produces `plan.md` beside an approved `spec.md`, from
[the template](../../../intent/_template/plan.md).

## Steps

1. Work read-only. In Claude Code use plan mode; in Copilot, ask for a plan with
   no edits. Read the spec, then the code and tests it touches.
2. *Files that change*: list every file with the reason. Add a new file only where
   no existing file fits.
3. *Order of work*:
   - smallest safe steps first;
   - the failing test before the code it proves;
   - one commit per step, ending with the `Intent:` and `Assisted-by:` trailers.
4. *Risks*: what could break (lifecycle runs, policies, publications, CI), and how
   each step avoids or detects it.
5. *Proof*: the exact commands from `AGENTS.md`, with the expected result for each
   acceptance criterion.
6. *Rollback*: `git revert` of the intent's commits, plus any operational undo.
7. Present the plan and wait for it to be accepted. Then set the status to
   `planned` and update the index.
8. During the build, if reality differs from the plan, update `plan.md` in the
   same commit as the change.
9. When the work is done, fill in *Evidence* with the pasted results. Set
   `implemented`, or `verified` once every acceptance criterion has evidence.
