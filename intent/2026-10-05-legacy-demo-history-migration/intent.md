# Intent: Never migrate local demo history without an explicit request

- **Status:** retrospective
- **Originator:** @botlhale, while running the local demo
- **Product owner:** @botlhale
- **Date:** 2026-10-05
- **Source:** retrospective

## Problem

`python sh/local_demo.py` failed with a Delta schema mismatch on a checkout that
still held local history written before the `L_REP_CTY` anchor column existed. The
only way forward was to move or delete that history by hand, and an automatic fix
would have discarded history the operator had not chosen to give up.

## Proposed outcome

The demo detects history written with the old schema. By default it stops and
explains what to do. Only with `--migrate-legacy` does it move the old table aside
under `output/legacy/` and start a new history.

## Affected users and systems

Developers running the five-minute local demo; `sh/local_demo.py`; the local Delta
catalog it writes.

## Constraints

- Legacy history is never migrated or deleted implicitly (submission-history
  contract).
- The default path stays non-destructive.

## Open questions

None at the time.

## Retrospective record

Reconstructed on 6 October 2026 from the session request and the commit. No intent,
spec or plan existed when the change was made, and no gate approval is claimed
beyond the owner's request.

- **Change:** `cf6e681` adds the schema check and the `--migrate-legacy` flag, and
  documents the flag in the README.
- **Evidence:** `tests/test_submission_history.py::test_local_demo_moves_pre_anchor_history_only_on_explicit_migration`;
  eval case `legacy-history-gate`.
