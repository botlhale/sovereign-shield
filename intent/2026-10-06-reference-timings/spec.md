# Spec: Publish the 6 October lifecycle timings as the current reference

- **Intent:** [intent.md](intent.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Approved by:** @botlhale, 2026-10-06
- **Skills applied:** none yet; the agent skills arrive with the AI-native SDLC
  intent. The documentation rules in CONTRIBUTING and the evidence register were
  applied directly.

## Requirements

- **R1.** Every current-reference statement gives about 42 minutes up and about
  35 minutes down for the 6 October 2026 cycle, with prerequisites already in
  place, and US$10 or less in Azure charges.
- **R2.** The evidence register (`docs/RELEASE_EVIDENCE.md`) records both cycles:
  6 October 2026 as current and 18 September 2026 as history. For each it states
  the platform, what the time includes, that the values are operator-reported, and
  that no line-item billing export exists.
- **R3.** The dated records (`docs/LIVE_DEPLOYMENT_2026_09_15.md` and
  `docs/LIVE_DEPLOYMENT_2026_09_18.md`) keep the 18 September figures, name that
  date, and point to the evidence register for later cycles.
- **R4.** The compute figure shows the new values and their prerequisite scope. Its
  PNG is re-rendered from the edited SVG, and only its manifest entry changes.
- **R5.** The documentation contract test pins the new measures.
- **R6.** The wording stays an observed synthetic result: no SLA, price ceiling or
  production estimate.

## Design

- **Shared phrasing.** "About 42 minutes up with prerequisites already in place,
  35 minutes down and US$10 or less in Azure charges." Bring-up covers all eight
  stages, including the offline test suite. The prerequisites are the state backend,
  the Entra persona users and the Databricks account identities.
- **Executive Brief.** Keep the sentence about the same length so the brief stays
  at eight pages.
- **Persona demo narration.** Spoken form: "forty-two" and "thirty-five".
- **Figure.**
  - Label: "SYNTHETIC REFERENCE CYCLE · 6 OCTOBER 2026".
  - Headline: "~42 minutes up · ~35 minutes down · US$10 or less in Azure charges".
  - Note: "Prerequisites already in place. Observed evaluation results, not an SLA,
    price ceiling or throughput benchmark."
  - Update the SVG `desc` to match.
- **Rendering.** Use the same headless Chrome command as
  `sh/verify_docs.py --render-diagrams`, for this figure only. Re-rendering every
  figure on this Linux machine would change the font in all six PNGs.
- **Teardown time.** The provenance paragraph explains why teardown went from about
  30 to about 35 minutes: down now waits for Azure to confirm that the Container Apps
  environment and the workspace are deleted.

## Flagged concerns

| Concern | Policy owner | Resolution |
| --- | --- | --- |
| The Linux render falls back to Liberation Sans; the other figures were rendered with Segoe UI | @botlhale (publication owner) | Accepted for this figure. Re-render every figure on one machine before the next publication release |
| The Executive Brief proof on Linux may paginate differently from Windows | @botlhale | Run `--print-proof`. If the brief is not eight pages, render the previous brief on the same machine before concluding the edit caused it |

## Acceptance criteria

- **R1:** A search for "75 minutes" or "30 minutes" finds only dated history: the
  dated records, the evidence-register history, and the unrelated Terraform timeout
  comment.
- **R2:** The evidence-register rows for bring-up and teardown name both dates.
- **R3:** Both dated records contain "18 September 2026" and a link to the
  evidence register.
- **R4:** `test_publication_diagrams_match_their_source_manifest` passes, and
  `git diff --stat docs/figures` lists only `compute_strategy.svg`,
  `compute_strategy.png` and `manifest.json`.
- **R5:** `test_primary_publications_preserve_enterprise_scope` checks
  "42 minutes", "35 minutes", "US$10" and "prerequisite".
- **R6:** Reviewed against the Documentation Changes rules in CONTRIBUTING.

## Out of scope

- Re-measuring the cycle or obtaining a billing export.
- Re-rendering the other figures.
- The Terraform comment about the 30-minute default delete timeout, which concerns
  a provider default, not the reference cycle.
