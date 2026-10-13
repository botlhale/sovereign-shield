# Intent: Link the publication PDFs to repository Markdown on GitHub

- **Status:** planned
- **Originator:** @botlhale
- **Product owner:** @botlhale
- **Date:** 2026-10-13
- **Source:** request

## Problem

The Executive Brief and white paper PDFs link to repository documents such as
`RELEASE_EVIDENCE.md` and `SECURITY.md`. In the committed PDFs those links point
to `file:///home/runner/...` paths on the machine that rendered the proof, so a
reader who opens a PDF cannot follow them.

## Proposed outcome

Every link from a publication PDF to a repository file or folder opens that file
or folder on GitHub, including its heading anchor.

## Affected users and systems

- Readers of `docs/EXECUTIVE_BRIEF.pdf` and
  `docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.pdf`.
- The proof renderer in `sh/verify_docs.py --print-proof`.

## Constraints

- The Markdown sources keep relative links, so `sh/verify_docs.py` still checks
  them and they work on GitHub.
- Images still load from the local checkout when the proof is rendered.
- The Executive Brief stays at eight pages.

## Open questions

None. The links target the `main` branch of `botlhale/sovereign-shield`, the
repository the brief already names.
