# CLAUDE.md

@AGENTS.md

## Claude Code Notes

- Start any non-trivial change in plan mode (Shift+Tab). Save the accepted plan as
  `plan.md` in the intent folder before editing code.
- Project hooks in `.claude/settings.json`:
  - ask before cloud lifecycle commands, publishing commands and policy-file edits;
  - deny reads of credential files;
  - lock `tests/` and `evals/` in fix mode.

  When a hook asks or denies, stop and say what needs approval. Never retry the
  action another way.
- Subagents in `.claude/agents/`:
  - `verifier` runs the verification block and reports without editing;
  - `policy-reviewer` reviews a diff against `REVIEW.md` before a pull request.
- When the same correction is needed twice, add it to "Things Agents Get Wrong" in
  `AGENTS.md`, not here, so every agent learns it.
