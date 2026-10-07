# Intent: Run the greenfield lifecycle from Linux with PowerShell 7

- **Status:** retrospective
- **Originator:** @botlhale, moving cloud operations from Windows to Ubuntu Linux
- **Product owner:** @botlhale
- **Date:** 2026-10-05
- **Source:** retrospective

## Problem

`sh/sovereignshield_up.ps1` assumed Windows. On Ubuntu with PowerShell 7:

- Stage 0 looked for `.venv\Scripts\python.exe`;
- the checkout lifecycle lock, an flock on Linux, blocked the offline suite, whose
  tests exercise scripts that take the same lock;
- the Easy Auth token-store secret went through `cmd.exe`;
- the first `az databricks` call waited at an extension-install prompt that the
  captured output hid, so the run appeared to hang.

## Proposed outcome

Both lifecycle scripts run unchanged from Windows PowerShell or from `pwsh` on
Linux, and no step waits on an invisible prompt.

## Affected users and systems

Operators of `sh/sovereignshield_up.ps1` and `sh/sovereignshield_down.ps1`;
`sh/container_apps_deploy.ps1`, `sh/databricks_account_setup.ps1` and the
orchestration module.

## Constraints

- Windows behavior, including the `cmd.exe` call that passes the SAS URL, stays the
  same.
- The secret is never written to a file or to the console.

## Open questions

None at the time.

## Retrospective record

Reconstructed on 6 October 2026 from the session requests and the commits. No intent,
spec or plan existed when the changes were made, and no gate approval is claimed
beyond the owner's requests.

- **Changes:**
  - `0e5b228` resolves Python portably in Stage 0, takes the lock after Stage 0,
    and passes the Easy Auth secret through `cmd.exe` only on Windows.
  - `7dbae8b` installs the `az databricks` extension before first use.
- **Evidence:**
  - `tests/test_deployment_boundaries.py::test_up_preflight_runs_on_linux_and_tests_before_taking_the_lock`
    and `::test_az_databricks_extension_is_installed_before_first_use`;
  - eval cases `linux-preflight-python` and `az-extension-prompt`;
  - the complete 6 October 2026 cycle ran from Ubuntu with PowerShell 7.6.
- **Later change:** `c38f3a7` takes the lock inside Stage 0, after the offline suite
  and before the first Azure change
  ([2026-10-06-lifecycle-lock-before-azure-changes](../2026-10-06-lifecycle-lock-before-azure-changes/intent.md)).
