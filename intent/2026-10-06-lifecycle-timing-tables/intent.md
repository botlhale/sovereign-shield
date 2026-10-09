# Intent: Show how long each lifecycle step takes

- **Status:** retrospective
- **Originator:** @botlhale, after the first Linux runs
- **Product owner:** @botlhale
- **Date:** 2026-10-06
- **Source:** retrospective

## Problem

The up and down scripts reported neither stage durations nor a total, so slow
steps and the published reference timings could not be checked against a run.

## Proposed outcome

Both scripts print a table of per-step durations, the time between steps, the total
and the start and finish times when they end, including after a failure, where
the failed step is marked incomplete.

## Affected users and systems

Operators of both greenfield lifecycle scripts; the reference timings in the
evidence register.

## Constraints

- Timing output must not change a run's outcome or mask its original error.

## Open questions

None at the time.

## Retrospective record

Reconstructed on 6 October 2026 from the session request and the commit. No intent,
spec or plan existed when the change was made, and no gate approval is claimed
beyond the owner's request.

- **Change:** `dad522d` adds `Write-SovereignShieldTimingSummary` and per-step
  timers to both scripts.
- **Evidence:** the 6 October 2026 cycle printed both tables. The later timing
  record (intent `2026-10-06-ai-native-sdlc`) builds on them, and
  `tests/test_lifecycle_bands.py` checks that the record follows the summary.
