# Plan: Publish the Gemini renders that pass review and fix the promising rest

- **Spec:** [spec.md](spec.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-08
- **Accepted by:** @botlhale, 2026-10-08 (request)

## Files that change

| File | Change |
| --- | --- |
| `docs/figures/ai/four_audiences.jpg`, `docs/figures/ai/triple_lock_illustration.jpg` | The two renders that pass, copied unchanged |
| `docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md` | Figure 4 image and caption |
| `docs/LINKEDIN_POST.md` | Cover and inline image |
| `docs/figures/README.md` | AI-generated illustrations and their provenance |
| `docs/figures/gemini_image_prompts.md` | Eight dated verdicts; four correction blocks |
| `tests/test_documentation_contract.py` | Figure list; provenance and caption test |

## Order of work

1. Change the tests and commit them failing.
2. Copy the two renders, update the publications, the README and the assessment.
3. Run the documentation tests, the link check and the print proof, then commit.

## Risks

| Risk | Mitigation |
| --- | --- |
| A larger figure pushes Figure 4's caption onto another page | `--print-proof` checks that every figure shares a page with an image |
| The repository grows by about 4.4 MB | Only renders in use are committed |
| A later edit embeds an AI image without a caption | The new test fails |

## Proof

```bash
.venv/bin/python -m pytest tests/test_documentation_contract.py -p no:cacheprovider -o addopts=""
.venv/bin/python sh/verify_docs.py
.venv/bin/python sh/verify_docs.py --print-proof
```

## Rollback

Revert the commits with `Intent: 2026-10-08-gemini-renders-round-two`. The
hand-authored figures were never changed.

## Evidence

Verified on 8 October 2026.

- **Review.** All eight renders are 2752x1536. Small text was proof-read from
  full-resolution crops. Three pass every check: F, B and engagement Figure B.
  Four are promising and got correction blocks: A, C, D and E. Engagement
  Figure A was not pursued. The verdicts are in the assessment table.
- **Published, unedited.**
  - `four_audiences.jpg` (SHA-256 `b0a4ff57…`) is the LinkedIn cover.
  - `triple_lock_illustration.jpg` (SHA-256 `f90a1d84…`) is White Paper Figure 4
    and the LinkedIn inline image.
- **Tests.** The two tests changed in `2163808` failed there. Documentation,
  SDLC and secret-scan tests now pass: 108 passed. `sh/verify_docs.py` verified
  481 links and anchors.
- **Print proof.** The Executive Brief stays at 8 pages. The White Paper proof is
  20 pages, and every figure shares a page with its image.
