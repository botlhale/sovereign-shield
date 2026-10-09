# Intent: Make teardown and rebuild finish without manual recovery

- **Status:** retrospective
- **Originator:** @botlhale, after failed down and up runs on 6 October 2026
- **Product owner:** @botlhale
- **Date:** 2026-10-06
- **Source:** retrospective

## Problem

Four cloud incidents stopped the lifecycle on 6 October 2026:

1. The workspace stayed in Deleting and `terraform destroy` timed out after 30
   minutes. Azure retained the workspace's default Unity Catalog storage, and file
   events kept recreating an Event Grid topic on it.
2. A rerun of down failed with `ApplianceBeingDeleted` while the first delete was
   still running.
3. Stage 1 of up failed twice: a new workspace grants its admins SQL access only
   minutes after creation.
4. Down's final check found the Container Apps environment 13 seconds before Azure
   finished removing it. `az containerapp env delete` stops polling after about 20
   minutes, and Azure took 27.

## Proposed outcome

A workload teardown and a greenfield bring-up each complete in one run, with
bounded waits that fail with a clear message instead of timing out silently.

## Affected users and systems

Operators of both lifecycle scripts; the Terraform workspace module and provider
configuration; the Azure resources of the workload.

## Constraints

- Every wait has a deadline and a re-check, because `az ... wait` exits 0 on
  timeout.
- Teardown removes only workload resources; the state backend and account
  identities stay.

## Open questions

None at the time.

## Retrospective record

Reconstructed on 6 October 2026 from the session reports and the commits. No intent,
spec or plan existed when the changes were made, and no gate approval is claimed
beyond the owner's requests to fix each failure.

- **Changes:**
  - `25058f8` force-deletes the workspace with a 60-minute delete timeout, and skips
    workspace API steps unless the workspace is Succeeded.
  - `b7e7d33` waits for an in-progress workspace delete and re-checks before
    `terraform destroy`.
  - `1e744d0` polls for SQL access for up to 15 minutes before the Stage 1 retry.
  - `7810503` polls ARM for up to 45 minutes until the Container Apps environment
    is gone.
- **Evidence:**
  - four regression tests in `tests/test_deployment_boundaries.py`;
  - eval cases `workspace-force-delete`, `workspace-delete-wait`,
    `stage1-sql-access-wait` and `containerapp-env-wait`;
  - the next cycle completed: about 35 minutes down and 42 minutes up
    (intent `2026-10-06-reference-timings`).
