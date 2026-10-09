---
name: sdmx-contract
description: Rules for the pinned BIS LBS structure, codelists, synthetic fixtures, SDMx validation rules and SDMx serialization. Use before changing src/lbs_contract.py, src/sdmx_rule_validator.py, src/decimal_measures.py, src/sdmx_ml_exporter.py, src/generate_sovereign_submissions.py, src/reference_data/ or the export formats.
---

# SDMx Contract

Sources of truth:

- [Synthetic information contract](../../../.github/skills/mvsd_specification.md)
- [SDMx submission validation contract](../../../.github/skills/sdmx_lbs_validation.md)

## Rules

- **Intake.** The modeled international intake is SDMx files only. The synthetic
  micro-transactions are educational fixtures, not a deliverable.
- **Key order.** Preserve the eleven-dimension BIS LBS key order.
- **Structure refresh.** Refresh the pinned structure only through
  `sh/refresh_lbs_contract.py`. Review the generated diff and never read an
  unreviewed `latest` at runtime.
- **Two kinds of compliance.** Keep format compliance and business-rule
  validation separate.
  - Parse published rule metadata; do not transcribe it.
  - The six cross-collection checks are unsupported. Say so; do not imply
    coverage.
- **Outbound formats.** An outbound format change needs a round-trip or schema
  test.
- **Citations.** Cite the authoritative standard or artifact in the spec.
- **Fixtures.** Use only real, permitted codelist values, so failures are genuine
  arithmetic inconsistencies.

## Checks

```bash
python -m pytest tests/test_sdmx_validation_rules.py tests/test_input_contract.py tests/test_api_gateway.py -p no:cacheprovider -o addopts=""
```
