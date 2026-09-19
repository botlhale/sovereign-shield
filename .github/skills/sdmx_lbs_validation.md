# SDMx Submission Validation Contract

Use this reference for structure, rule interpretation, feedback and serialization.
The owner is [sdmx_rule_validator.py](../../src/sdmx_rule_validator.py), supported by
[lbs_contract.py](../../src/lbs_contract.py) and
[decimal_measures.py](../../src/decimal_measures.py).

## Submission Scope

The modeled international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely as educational calculation fixtures, not input
required by the receiving organization or a system deliverable. The receiver
validates the submitted observations independently of the fixture generator.
Confidentiality is sender-owned; arithmetic acceptance is a separate result.

## Four Validation Layers

| Layer | Current Implementation | Limit |
| --- | --- | --- |
| Message format | pysdmx 1.18.0 XML validation enabled; exactly one dataset; supported DSD/dataflow and actions | Not formal standards certification |
| Structure | Reviewed BIS LBS 1.0 components, order, required metadata and canonical eleven-part key | Extracted snapshot is not a full registry |
| Codes and reference profile | Pinned codelists, sender-country mapping, periods, duplicates and decimal values | Complete dataflow/provision-agreement content constraints remain unimplemented |
| Arithmetic | Workbook interpreter evaluates 21 within-dataset rules | Six cross-collection checks unsupported; missing breakdowns explicitly not evaluated |

Runtime uses [the pinned contract](../../src/reference_data/lbs_structure.json).
Refresh deliberately using [refresh_lbs_contract.py](../../sh/refresh_lbs_contract.py),
review the diff/provenance and rerun tests. An unreviewed `latest` registry response
or a dimension-list-only fallback must not become the validation authority.

## Arithmetic and Decimal Semantics

Rule IDs are `LBS_CC01`-`LBS_CC03` and `LBS_CC:04`-`LBS_CC:21`, preserving source
spelling. Cross-collection `LBS_CC:22`-`:27` remain unsupported. Workbook parsing
does not establish semantic completeness: placeholder, residual, breakdown and
content-constraint interpretations require independent domain review.

Measures use decimal arithmetic and `DECIMAL(38,3)`, with half-up intake rounding.
Three-place precision is the demonstrator's profile, not universal SDMx policy.
Signed and genuine zero values are retained; sign alone is not an arithmetic
failure. Masked/missing values are not zero.

The synthetic generator illustrates confidentiality classification using absolute
contributions and a 0.60 dominance threshold. This is educational, not a receiving
rule, an international reporting mandate or a complete disclosure methodology.

## Verdict and Analyst Feedback

One submission contains one nonempty full country/period/aggregation snapshot.
Arithmetic failure assigns `QUALITY_STATUS=FAIL` and `BATCH_STATUS=QUARANTINE`
across that batch. `FAILED_RULE_ID` identifies offending observations;
`BATCH_FAILED_RULE_ID` provides the collective reason; `VALIDATION_NOTES` records
evaluation coverage. Clean batches use `PASS` / `PUBLISHED`.

The Analyst View reconciles the latest filing expected by a submitter with the
receiver's actual IDs, submitted/received timestamps, values and verdict. Rejection
does not replace the prior current accepted publication. Full receipt/sequence
attestation is an institutional design requirement, not supplied by processing time.

## Serialization

[sdmx_ml_exporter.py](../../src/sdmx_ml_exporter.py) emits current published
SDMx-ML 3.0, SDMx-JSON 2.0 and SDMx-CSV 2.0. Audit CSV is separate. Standard
formats reject rejected/noncurrent rows and duplicate observation keys.
Normal exports use pinned offline structure components, not an unvalidated
ElementTree fallback. Empty exports return HTTP 204 at the gateway.

The reference profile includes `DECIMALS=3`, `UNIT_MEASURE=USD`, `UNIT_MULT=6`,
`COLLECTION=E`, `AVAILABILITY=A` and frequency-derived `TIME_FORMAT`. Currency
denomination is a dimension; no currency conversion is implied. Dataset-level
attributes must be passed through pysdmx dataset attributes, not merely frame columns.

Masking prevents direct value access, not reconstruction from public totals or
researcher-visible row existence. Apply the [disclosure challenge](../../SECURITY.md#statistical-reconstruction-challenge)
and restrict/remove the Researcher role where required by the data authority.

See [input tests](../../tests/test_input_contract.py),
[arithmetic/wire tests](../../tests/test_sdmx_validation_rules.py) and
[release evidence](../../docs/RELEASE_EVIDENCE.md).