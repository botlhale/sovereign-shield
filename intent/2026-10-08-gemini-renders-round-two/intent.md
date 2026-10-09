# Intent: Publish the Gemini renders that pass review and fix the promising rest

- **Status:** planned
- **Originator:** @botlhale, after generating eight new renders from the repository prompts
- **Product owner:** @botlhale
- **Date:** 2026-10-08
- **Source:** request

## Problem

Eight new Gemini renders sit in the uncommitted `docs/aiimages/` folder, one for
each of prompts A to F and engagement Figures A and B. Each still has to be checked
against its prompt, the reference contracts and the publication checklist. Only
then can it replace the figure the repository currently uses in the same place.

## Proposed outcome

Every render that passes all six checklist items, and looks better than the figure
it would replace in that place, is committed with its provenance and used there,
captioned as an AI-generated illustration. Each promising render that fails gets a
dated verdict and an exact correction. The others get a recorded reason they are
not pursued.

## Affected users and systems

Readers of the White Paper and the LinkedIn article; `docs/figures/`,
`docs/figures/gemini_image_prompts.md`, `docs/LINKEDIN_POST.md`, the documentation
contract tests.

## Constraints

- Hand-authored SVG figures remain the architectural reference and stay in the
  repository.
- No generated label becomes a claim the code or the contracts do not support.
- No logos or trademarks. Each published image carries an "AI-generated
  illustration" caption and a provenance record.
- `docs/aiimages/` itself stays uncommitted.

## Open questions

Answered by the product owner on 8 October 2026: use a render instead of the
current figure only if it is correct and more appealing; otherwise say what is off,
and how to fix it, for the promising ones.
