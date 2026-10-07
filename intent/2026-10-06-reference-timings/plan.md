# Plan: Publish the 6 October lifecycle timings as the current reference

- **Spec:** [spec.md](spec.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Accepted by:** @botlhale, 2026-10-06

## Files that change

| File | Change |
| --- | --- |
| `tests/test_documentation_contract.py` | Pin "42 minutes" and "35 minutes" instead of 75 and 30 |
| `docs/RELEASE_EVIDENCE.md` | Bring-up and teardown rows name both cycles; provenance covers both |
| `README.md` | Deploy section sentence |
| `docs/EXECUTIVE_BRIEF.md` | Reference evaluation sentence, same length |
| `docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md` | Implementation status line and the reproducible deployment paragraph |
| `docs/AUTOMATION_RUNBOOK.md` | Reference evaluation paragraph |
| `docs/RESOURCE_PROVENANCE.md` | Container Apps cost paragraph |
| `.github/skills/SKILLS.md` | Deployment and portability paragraph |
| `docs/PERSONA_DEMO_SCRIPT.md` | Closing narration |
| `docs/LINKEDIN_POST.md` | Post sentence |
| `docs/LIVE_DEPLOYMENT_2026_09_15.md`, `docs/LIVE_DEPLOYMENT_2026_09_18.md` | Date the 18 September figures; point to the evidence register |
| `docs/figures/compute_strategy.svg`, `.png`, `docs/figures/manifest.json` | Figure text, re-render, one manifest entry |

## Order of work

1. Change the contract test and confirm it fails against the current documents.
2. Update the evidence register, the owning document for measured results.
3. Update the three primary publications, then the other current-reference
   documents.
4. Date the historical records without changing their figures.
5. Edit the SVG, render this figure only with headless Chrome, and update its
   manifest entry with the digests `sh/verify_docs.py` uses.
6. Run the proof commands.

## Risks

| Risk | Mitigation |
| --- | --- |
| An occurrence is missed | Search the repository for 75/30-minute wording, spelled-out numbers and "~75" before committing |
| Historical figures are rewritten | Edit only the sentences that state the current cycle; dated records gain a date and a link |
| The brief grows past eight pages | Keep the sentence length; run `--print-proof` |
| The figure text overflows in the fallback font | Lines stay well inside the 1,472-pixel panel. Check the render's dimensions and digest |
| The full re-render changes every PNG | Render only `compute_strategy.svg` |

## Proof

```bash
.venv/bin/python -m pytest tests/test_documentation_contract.py -p no:cacheprovider -o addopts=""
.venv/bin/python sh/verify_docs.py
.venv/bin/python sh/verify_docs.py --print-proof
git grep -nE "75 minutes|30 minutes|seventy-five|~75" -- . ':!docs/aiimages'
.venv/bin/python -m pytest tests/ -p no:cacheprovider -o addopts=""
```

## Rollback

Revert the implementing commit (`git log --grep "Intent: 2026-10-06-reference-timings"`).
No operational state changes.

## Evidence

Verified on 6 October 2026, before the implementing commit.

- The contract test was changed first and failed for all three publications.
  After the edits, `tests/test_documentation_contract.py` passed 16 of 16.
- `sh/verify_docs.py` verified 388 local links and anchors. `--print-proof`
  produced an eight-page Executive Brief and a 20-page white paper, with each
  figure on a page that has an image.
- `git grep` for the old wording finds only the dated records, the
  evidence-register history and these intent records.
- `git diff --stat docs/figures` lists only `compute_strategy.svg`,
  `compute_strategy.png` and `manifest.json`.
  - Text extents were measured in the same headless Chrome: the widest panel line
    ends at x=1005 of 1536.
  - The render used Lato, the third font in the SVG stack, because Inter and
    Segoe UI are not installed on this Linux machine. The other five figures keep
    their earlier Segoe UI renders.
- Full offline suite: 275 passed, 13 skipped.
