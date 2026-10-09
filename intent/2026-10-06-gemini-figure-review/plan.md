# Plan: Decide whether the new Gemini engagement figures can be published

- **Spec:** [spec.md](spec.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Accepted by:** @botlhale, 2026-10-06

## Files that change

| File | Change |
| --- | --- |
| `docs/figures/gemini_image_prompts.md` | Three dated assessment rows; correction blocks under the Figure A and Figure B prompts |

## Order of work

1. Compare each render with its verified review draft, node by node and arrow by
   arrow, then apply the remaining checklist items.
2. Record the verdicts.
3. Add the correction blocks to the prompts.
4. Report the follow-up edit prompts to the product owner.

## Risks

| Risk | Mitigation |
| --- | --- |
| A render is misidentified | Identification follows creation time and attachment order, and is stated in the spec |
| A near-miss render is published | No render is committed unless it passes every check |
| The prompt edits change the specified topology | Corrections restate the existing allowed routes; no labels or arrows are added |

## Proof

```bash
.venv/bin/python -m pytest tests/test_documentation_contract.py -p no:cacheprovider -o addopts=""
.venv/bin/python sh/verify_docs.py
git status --short docs/aiimages  # still untracked
```

## Rollback

Revert the implementing commit. No figures or publications change.

## Evidence

Verified on 6 October 2026, before the implementing commit. Each render was compared
with `docs/figures/review/engagement_workflow.svg` or `submission_reconciliation.svg`,
node by node and arrow by arrow.

- Figure A (`…l71f3ml71f3ml71f.jpeg`) fails Topology, Ownership and Text. Not
  integrated.
- Figure B, first render (`…x39tprx39tprx39t.jpeg`), fails Text: leaked "Title:" and
  "Subtitle:" prefixes and printed node IDs. Not integrated.
- Figure B, refined render (`…yhwrbnyhwrbnyhwr.jpeg`), fails Text: printed node IDs
  and one misplaced annotation. It is two edits from publishable. Not integrated.
- `git status --short docs/aiimages` reports `?? docs/aiimages/`: no render is
  committed.
- `tests/test_documentation_contract.py` passed 16 of 16. `sh/verify_docs.py`
  verified 455 local links and anchors.
- The follow-up edit prompts for each render went to the product owner with this
  change.
