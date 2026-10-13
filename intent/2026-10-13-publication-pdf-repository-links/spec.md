# Spec: Link the publication PDFs to repository Markdown on GitHub

- **Intent:** [intent.md](intent.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-13
- **Approved by:** @botlhale, 2026-10-13 (request)
- **Skills applied:** `evidence-and-claims`

## Requirements

- **R1.** When the proof HTML is rendered, a relative link to a repository file
  becomes `https://github.com/botlhale/sovereign-shield/blob/main/<path>`, and a
  link to a folder becomes `.../tree/main/<path>`. The heading anchor is kept.
- **R2.** Absolute URLs, `mailto:` links and same-page anchors are unchanged.
- **R3.** Images keep their relative source so the proof embeds the local files.
- **R4.** The committed PDFs are re-rendered and contain no `file://` links.

## Design

`sh/verify_docs.py` gains a `publication_html(source)` function that parses the
Markdown, rewrites the `href` of each relative `link_open` token against the
repository root, and renders the tokens. `render_proofs` uses it. The `<base>`
element stays, so image sources resolve locally.

## Flagged concerns

| Concern | Policy owner | Resolution |
| --- | --- | --- |
| None | | |

## Acceptance criteria

- R1, R2, R3 -> `tests/test_documentation_contract.py` renders both publications
  and checks every link and image.
- R4 -> the committed PDFs' link annotations contain only `https://` URLs, and
  `sh/verify_docs.py --print-proof` keeps the brief at eight pages.

## Out of scope

Raw HTML anchors inside the Markdown (the publications have none) and the other
documents, which are not printed.
