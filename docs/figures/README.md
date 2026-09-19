# Publication Diagram Sources

These diagrams replace the earlier conceptual artwork with the current
information, policy and deployment contracts. They are schematics, not live
screenshots. The [portal capture inventory](../../demo/README.md) covers the
unaltered synthetic screenshots separately.

The separate [engagement review gallery](review/README.md) contains two 3840x2160
drafts with editable sources. They are not yet replacements for the publication
figures below. Render them with `--render-diagrams --diagram-set review`.

| Figure | Editable Source | Publication Image |
| --- | --- | --- |
| Governed SDMx exchange | [SVG](executive_architecture.svg) | [PNG](executive_architecture.png) |
| Synthetic-first engagement | [SVG](engagement_boundary.svg) | [PNG](engagement_boundary.png) |
| Two hosts and identities | [SVG](dual_consumption.svg) | [PNG](dual_consumption.png) |
| Triple-lock contract | [SVG](triple_lock.svg) | [PNG](triple_lock.png) |
| Atomic submission transition | [SVG](submission_history.svg) | [PNG](submission_history.png) |
| Compute and evaluation limits | [SVG](compute_strategy.svg) | [PNG](compute_strategy.png) |

The SVGs include text descriptions and use local fonts. PNGs are rendered at
1600x900 with the installed Chrome executable. The generated [manifest](manifest.json)
records LF-normalized source and binary image SHA-256 digests so documentation
tests detect stale renders. Git attributes preserve LF for source checkouts.
Browser/font changes can alter pixels; hashes identify the committed
render, not a universal cross-platform pixel identity guarantee.

```powershell
.venv\Scripts\python.exe sh/verify_docs.py --render-diagrams --print-proof
.venv\Scripts\python.exe -m pytest tests/test_documentation_contract.py
```

Review text bounds, arrows and PDF placement after any source edit. Update the
[Mermaid architecture specification](../ARCHITECTURE_DIAGRAMS.md) when a control
or flow changes. The [engagement image prompt](../ENGAGEMENT_WORKFLOW_IMAGE_PROMPT.md)
is available for an alternative professionally reviewed rendering; AI-generated
labels are not the architectural authority.

The diagrams deliberately exclude unimplemented ABAC tags, cryptographic lineage,
an air-gap claim, year-9999 intervals and automatic production readiness. The
international intake is SDMx files only; synthetic micro-transactions are
educational artifacts, not deliverables. Public values and row existence remain
subject to disclosure review despite correct entitlements.