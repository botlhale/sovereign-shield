# Publication Figures

Hand-authored SVG schematics used by the [Executive Brief](../EXECUTIVE_BRIEF.md),
[White Paper](../whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md) and
[README](../../README.md). They share one palette with the Mermaid
[architecture diagrams](../ARCHITECTURE_DIAGRAMS.md): slate for intake, teal for Unity
Catalog governance, indigo for serving and provider work, sky for persona outputs and amber
for limits. Portal screenshots have a separate [capture inventory](../../demo/README.md).

| Figure | Source | Image |
| --- | --- | --- |
| Governed SDMx exchange in four planes | [SVG](executive_architecture.svg) | [PNG](executive_architecture.png) |
| The contractor dilemma | [SVG](engagement_boundary.svg) | [PNG](engagement_boundary.png) |
| Dual consumption, one governed store | [SVG](dual_consumption.svg) | [PNG](dual_consumption.png) |
| Triple-lock control contract | [SVG](triple_lock.svg) | [PNG](triple_lock.png) |
| One atomic transition per filing | [SVG](submission_history.svg) | [PNG](submission_history.png) |
| Evaluation compute and scale decisions | [SVG](compute_strategy.svg) | [PNG](compute_strategy.png) |

The [review gallery](review/README.md) holds two 3840x2160 engagement figures that are not
yet in the publications. [Image-generation prompts](gemini_image_prompts.md) cover optional
AI-generated artwork; generated labels are never the architectural authority.

## Render and Verify

PNGs are rendered at 1600x900 with headless Chrome or Chromium (set `CHROME_BIN` if it is not
on `PATH`). The [manifest](manifest.json) records LF-normalized source and PNG SHA-256
digests, so the documentation tests detect a stale render. Fonts differ between machines;
the digests identify the committed render, not a cross-platform pixel guarantee.

```bash
pip install -r sh/requirements-docs.txt
python sh/verify_docs.py --render-diagrams                        # publication set
python sh/verify_docs.py --render-diagrams --diagram-set review   # review set
pytest tests/test_documentation_contract.py
```

After editing a source, check text bounds and arrows at full size and in the PDF proofs
(`--print-proof`). The figures deliberately omit unimplemented controls: ABAC tags,
cryptographic lineage, an air-gap claim and automatic production readiness. The Secure Data
Enclave appears only as a dashed concept.
