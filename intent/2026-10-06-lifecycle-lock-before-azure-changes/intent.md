# Intent: Lock before Stage 0 changes Azure and stop teardown on failed Azure CLI queries

- **Status:** retrospective
- **Originator:** @botlhale, through a Copilot cloud agent session
- **Product owner:** @botlhale
- **Date:** 2026-10-06
- **Source:** retrospective

## Problem

- `up` took the checkout lifecycle lock only after Stage 0, but Stage 0 already
  changes the subscription by registering resource providers. Two runs from one
  checkout could both reach Azure.
- `down` read a failed `az` query as an empty answer. Workspace discovery, the
  resource-group check in the Container Apps wait and the workspace state check
  could then skip steps or end a wait early.
- The solution audit still called the greenfield path Windows-bound.

## Proposed outcome

`up` runs the offline suite, then takes the lock before the first Azure change.
Every `az` query that drives a teardown decision fails the run when the query
itself fails. The audit reflects Linux support.

## Affected users and systems

Operators of both greenfield lifecycle scripts; `docs/solution_audit.md`.

## Constraints

- The offline suite still runs before the lock, which is an flock on Linux.
- A run that starts after Stage 0 still takes the lock.

## Open questions

None at the time.

## Retrospective record

Reconstructed on 6 October 2026 from the commits. The changes were made in a separate
Copilot cloud agent session, pushed to `mosb_dev` and merged to `main` in pull request
#7, while this branch built the AI-native SDLC. No intent, spec or plan existed at the
time.

- **Changes:** `c38f3a7` moves the lock and adds the exit-code checks, and
  strengthens the legacy-history migration test. `c8672de` updates the audit
  scorecard.
- **Integration:** `52947d9` merges them into this branch. The follow-up commit:
  - rewrites `test_up_preflight_runs_on_linux_and_tests_before_taking_the_lock` for
    the new lock position;
  - adds `test_down_stops_when_an_azure_cli_query_fails`;
  - updates the `workspace-delete-wait` and `containerapp-env-wait` eval defects to
    the new code;
  - corrects the audit's reference-run platforms to match the evidence register.
- **Refines:** the lock placement of `0e5b228`
  ([2026-10-05-linux-lifecycle](../2026-10-05-linux-lifecycle/intent.md)).
