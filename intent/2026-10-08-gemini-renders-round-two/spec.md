# Spec: Publish the Gemini renders that pass review and fix the promising rest

- **Intent:** [intent.md](intent.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-08
- **Approved by:** @botlhale, 2026-10-08 (request)
- **Skills applied:** `evidence-and-claims`

## Requirements

- **R1.** Check each render against its prompt, the
  [triple-lock contract](../../.github/skills/triple_lock_security.md) and the six
  checklist items. Proof-read small text from full-resolution crops.
- **R2.** A render replaces the current figure in a place only if:
  - it passes every check;
  - it is more appealing there;
  - that place's caption and text still hold.
- **R3.** Published renders live in `docs/figures/ai/`. The figures README records
  each one's prompt, date, size, reviewer and use. Every embed of one carries
  "AI-generated illustration".
- **R4.** The assessment table gains a dated row for each of the eight renders.
  Each promising render that fails gets a correction block under its prompt.
- **R5.** Tests pin the White Paper figure list and enforce the provenance and
  caption rule.

## Design

| Render | Verdict | Use |
| --- | --- | --- |
| F Executive Architecture | Passes | LinkedIn article cover, instead of the four-plane figure; the Brief and README keep the architecture figure their text describes |
| B Triple-Lock Security | Passes | White Paper Figure 4 and the LinkedIn inline image. Figure 4's caption already describes it; the persona matrix table that follows carries the detail. The hand-authored contract stays in the architecture gallery |
| Engagement Figure B | Passes | Not used: no publication shows Figure B, and the verified review draft encodes more |
| E Technical Architecture | Fails: Terraform logo, network-line background | Correction block |
| A Contractor Dilemma | Fails: review bypass, stray connector | Correction block |
| D Three Consumption Planes | Fails: leaked position words | Correction block |
| C Submission History | Fails: open interval drawn closed | Correction block |
| Engagement Figure A | Fails: five topology errors | Not pursued; the verified SVG stays |

## Flagged concerns

| Concern | Policy owner | Resolution |
| --- | --- | --- |
| The White Paper's Figure 4 changes from a hand-authored schematic to an illustration, in a darker style than its neighbours | @botlhale (publication) | Accepted on request. The caption names it as AI-generated and links the hand-authored contract |
| The Triple-Lock render has a soft glow that the negative prompt discourages | @botlhale (publication) | Accepted as a style point; it alters no label or arrow |

## Acceptance criteria

| Requirement | Proof |
| --- | --- |
| R1, R2, R4 | Dated rows and correction blocks in `docs/figures/gemini_image_prompts.md` |
| R3, R5 | `tests/test_documentation_contract.py` |
| All | `sh/verify_docs.py` and `--print-proof`; the White Paper keeps every figure beside its caption |

## Out of scope

- Generating or editing images.
- Changing the hand-authored SVG figures.
