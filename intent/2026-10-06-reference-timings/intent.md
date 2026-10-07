# Intent: Publish the 6 October lifecycle timings as the current reference

- **Status:** accepted
- **Originator:** Project operator
- **Product owner:** @botlhale
- **Date:** 2026-10-06
- **Source:** request

## Problem

The publications say the greenfield lifecycle takes about 75 minutes up,
including prerequisite setup, and 30 minutes down. Those figures come from the
18 September 2026 evaluation run from Windows. The operator's 6 October 2026
cycle, run from Ubuntu Linux with PowerShell 7 after the teardown and bring-up
hardening, took about 42 minutes up and 35 minutes down with the prerequisites
already in place. Readers get an out-of-date expectation in both directions.

## Proposed outcome

Every statement of the current reference cycle gives about 42 minutes up and
35 minutes down for the 6 October cycle, with prerequisites already in place and
US$10 or less in Azure charges. This covers the publications, runbook, provenance
guide, reference index, demo narration, social post and compute figure. Dated
historical records keep their own figures and point to the current measurement.

## Affected users and systems

- Readers of the README, Executive Brief, white paper, operations runbook,
  resource provenance guide, reference index (`.github/skills/SKILLS.md`), persona
  demo script and LinkedIn post.
- `docs/figures/compute_strategy.svg`, its rendered PNG and its manifest entry.
- The documentation contract test that pins the published measures.

## Constraints

- Dated records stay historical (CONTRIBUTING, Documentation Changes).
- Measurements remain observed synthetic results, never an SLA or price ceiling.
- The Executive Brief keeps its eight designed pages.
- Figure digests in `docs/figures/manifest.json` must match source and image.

## Open questions

- What did the 6 October cycle cost? Answered by the product owner on
  6 October 2026: US$10 or less in Azure charges. No line-item billing export.
- Is a per-step breakdown available? The operator reported totals only. Recording
  every run is part of the AI-native SDLC intent.
