# Plan: Link the publication PDFs to repository Markdown on GitHub

- **Spec:** [spec.md](spec.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-13
- **Accepted by:** @botlhale, 2026-10-13 (request)

## Files that change

| File | Change |
| --- | --- |
| `tests/test_documentation_contract.py` | Rendered publication links point to GitHub; images stay local |
| `sh/verify_docs.py` | `publication_html` rewrites relative links; `render_proofs` uses it |
| `docs/EXECUTIVE_BRIEF.pdf`, `docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.pdf` | Re-rendered proofs |

## Order of work

1. Add the test and commit it failing.
2. Change `sh/verify_docs.py` and run the test.
3. Run `--print-proof`, copy both PDFs into `docs/` and check their links.

## Risks

| Risk | Mitigation |
| --- | --- |
| Images resolve to GitHub and the proof prints without them | Only `link_open` tokens change; the test checks image sources and `--print-proof` checks every white paper figure shares a page with an image |
| Links point to a branch that does not exist | `main` is the default branch named by the README clone command |

## Proof

```bash
python -m pytest tests/test_documentation_contract.py -p no:cacheprovider -o addopts=""
python sh/verify_docs.py --print-proof
```

## Rollback

Revert the commits with `Intent: 2026-10-13-publication-pdf-repository-links`.

## Evidence

Completed when the status becomes verified: commands run, results and commits.
