# Spec: Decide whether the new Gemini engagement figures can be published

- **Intent:** [intent.md](intent.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Approved by:** @botlhale, 2026-10-06
- **Skills applied:** none yet; the publication checklist in
  `docs/figures/gemini_image_prompts.md` and the verified review drafts were
  applied directly.

## Requirements

- **R1.** Assess each of the three renders against all six checklist items. Use
  `docs/figures/review/engagement_workflow.svg` and `submission_reconciliation.svg`
  as the topology and ownership reference.
- **R2.** Record a dated verdict for each render in *Assessment of Existing
  Renders*.
- **R3.** Integrate a render only if it passes every check.
- **R4.** For each render that fails, state how close it is and the follow-up
  edits that would close the gap.
- **R5.** Strengthen the Figure A and Figure B prompts against the failure modes
  observed, without changing the specified labels or topology.

## Design

- **Identify the renders.** Use creation time and attachment order:
  - `…l71f3ml71f3ml71f.jpeg` is Figure A;
  - `…x39tprx39tprx39t.jpeg` is the first Figure B;
  - `…yhwrbnyhwrbnyhwr.jpeg` is the refined Figure B.
- **Compare.** Map each node and arrow to the IDs in the verified drafts (A1–G3,
  S1–S8). Report differences by visible label, because the IDs must not be printed.
- **Record verdicts.** Add three rows dated 6 October 2026 to the assessment table.
- **Strengthen the prompts.** Add a short "Checks that failed before" block under
  each prompt, naming the exact corrections, for example "G3 approves C5, never C4".

## Flagged concerns

| Concern | Policy owner | Resolution |
| --- | --- | --- |
| Raster images cannot be checked automatically | @botlhale (publication owner) | Inspection by eye against the verified drafts, recorded in the table. A render is committed only after every check passes |

## Acceptance criteria

- **R1, R2:** The assessment table has three rows dated 6 October 2026, one per
  render, each naming the blocking defects or stating that the render passes.
- **R3:** No render is committed unless its row says it passes every check.
- **R4:** The final report to the product owner gives follow-up edit prompts for
  each failing render.
- **R5:** The prompts gain correction blocks. The documentation contract tests and
  `sh/verify_docs.py` pass.

## Out of scope

- Generating new images.
- Changing the verified review drafts or the publication figures.
