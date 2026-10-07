# Intent: Run the repository on the six-stage AI-native SDLC

- **Status:** planned
- **Originator:** @botlhale, as Enterprise Data Architect and Enterprise Information Architect
- **Product owner:** @botlhale
- **Date:** 2026-10-06
- **Source:** request

## Problem

AI agents already write most of the code, documentation and tests here, but the
process around them is implicit. Requests live in chat sessions, design decisions
in commit messages and agent guidance in people's heads. Today the repository has:

- no committed intent or specification to review a change against;
- no project instructions or skills that an agent loads automatically;
- no deterministic gate that stops an agent from running a cloud teardown,
  pushing, or editing a Unity Catalog policy file;
- no AI review against written criteria and no agent evals;
- no loop that turns lifecycle drift or scan findings into new work.

A reviewer cannot follow a change from request to production evidence.

## Proposed outcome

The repository follows the six stages of the
[AI-native SDLC playbook](https://academy.claude.com/courses/ai-native-sdlc-playbook):
Plan, Design, Build, Test, Deploy and Maintain. Each stage leaves a committed
artifact that the next stage reads. Deterministic controls enforce the gates that
must hold, and a named human approves at each gate. The maintainer can request
improvements by describing a problem to an agent and approving its drafts.

## Affected users and systems

- The maintainer and contributors, human or agent, using Claude Code or GitHub
  Copilot.
- Repository governance: pull request template, CONTRIBUTING, review criteria,
  code owners and workflows.
- The greenfield lifecycle scripts, which gain timing records, and the operations
  documentation.

## Constraints

- No secrets in the repository. AI workflows stay inert until a maintainer adds
  the API key secret.
- Existing gates stay in place: offline tests, `promote.yml` environment approval,
  action pinning and fail-closed controls.
- The reference notes in `.github/skills/` remain the source of truth for
  contracts. Agent skills point to them instead of copying them.
- One person holds every role. The record says so and does not imply separation
  of duties.
- Both Claude Code and GitHub Copilot are supported where their tools allow.

## Open questions

Answered by the product owner on 6 October 2026:

- Which agents? Both Claude Code and GitHub Copilot.
- AI review and evals in CI? Add workflows that skip cleanly until the
  `ANTHROPIC_API_KEY` secret exists.
- Who approves intents, specs, plans, policy skills and releases? @botlhale for
  every role, with that limitation stated.
- Which agent actions need a named human approval? Cloud lifecycle commands (up and
  down scripts, Terraform apply and destroy, Azure deletes), `git push`, edits to
  security policy files, and edits to tests while a bug is being fixed.
- Backfill records for earlier changes in this session? Yes, labelled retrospective
  with commit SHAs.
- Close the loop on lifecycle timings? Yes: record each run and draft an intent
  when a run is unusually slow.
