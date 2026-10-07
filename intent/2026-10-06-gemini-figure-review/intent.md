# Intent: Decide whether the new Gemini engagement figures can be published

- **Status:** verified
- **Originator:** @botlhale
- **Product owner:** @botlhale
- **Date:** 2026-10-06
- **Source:** request

## Problem

Three Gemini-generated renders of the engagement figures are in `docs/aiimages/`
(kept out of version control): one render of Figure A, the engagement workflow,
and two of Figure B, submission reconciliation. Nobody has checked them against
the verified review drafts in `docs/figures/review/` or the publication checklist
in `docs/figures/gemini_image_prompts.md`. Publishing a figure with a wrong
approval route or owner would misstate the engagement boundary.

## Proposed outcome

Each render has a recorded verdict against the checklist (text, topology,
ownership, claims, legibility, provenance). A render that passes is integrated,
and its source and approval are recorded. A render that fails gets a list of the
differences from the verified topology and the prompt changes or follow-up edits
that would close them.

## Affected users and systems

- Readers of the engagement playbook and publications, if a figure is integrated.
- `docs/figures/gemini_image_prompts.md`: its assessment table and prompts.

## Constraints

- The verified review drafts (`docs/figures/review/`) and their tests define the
  correct topology and ownership.
- Generated images are not evidence and are not committed unless they pass every
  check.
- `docs/aiimages/` stays out of version control.

## Open questions

- None. The verdict criteria already exist in the publication checklist.
