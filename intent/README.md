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

## Status Lifecycle

`draft` → `accepted` → `specified` → `planned` → `implemented` → `verified`, or
`rejected` at any point. The status lives in `intent.md` and in the index below.

`retrospective` marks a record written after the change shipped. It is
reconstructed from the original request and the commits, and it does not claim
gate approvals that did not happen at the time.

## Index

| Intent | Status | Summary |
| --- | --- | --- |
| [2026-10-06-reference-timings](2026-10-06-reference-timings/intent.md) | verified | Publish the 6 October lifecycle timings as the current reference |
| [2026-10-06-ai-native-sdlc](2026-10-06-ai-native-sdlc/intent.md) | planned | Run the repository on the six-stage AI-native SDLC |
| [2026-10-06-gemini-figure-review](2026-10-06-gemini-figure-review/intent.md) | planned | Decide whether the new Gemini engagement figures can be published |
