---
name: evidence-and-claims
description: Rules for measured results, publication wording, dated records and figures. Use before changing README.md, docs/ (Executive Brief, white paper, evidence register, runbooks, dated LIVE_DEPLOYMENT records), docs/figures/ SVGs and PNGs, or any statement of time, cost, coverage or security.
---

# Evidence and Claims

The [evidence register](../../../docs/RELEASE_EVIDENCE.md) owns measured results
and limitations. Other documents state a result and link to it.

## Rules

- **Generated text is not evidence.** A claim needs a test, a dated live record or
  a cited standard.
- **Wording.**
  - No SLA, price ceiling, certification, "guarantee" or "air-gapped" wording.
  - Synthetic results are observed results.
- **History.** Dated records (`docs/LIVE_DEPLOYMENT_*.md`) keep their own
  figures. Add a date or a link; never rewrite their numbers.
- **One owner per limitation.** State each limitation once, in its owning
  document, and link to it.
- **Publication contract.** The README, Executive Brief and white paper must keep
  the phrases pinned by `test_primary_publications_preserve_enterprise_scope`.
  Change the test first when a pinned measure changes.
- **Shared title.** The Executive Brief and the white paper share one title.
- **Page budget.** The brief stays at eight pages. Run
  `python sh/verify_docs.py --print-proof` after content, figure or layout edits.
- **Figures.**
  - Edit the SVG source, then re-render.
  - `--render-diagrams` re-renders every figure. When one figure changes, render
    only that figure with the same Chrome command and update its manifest entry.
- **Generated images.** Follow the checklist in
  [image prompts](../../../docs/figures/gemini_image_prompts.md). Commit an image
  only when it passes every check.

## Checks

```bash
python -m pytest tests/test_documentation_contract.py -p no:cacheprovider -o addopts=""
python sh/verify_docs.py
```
