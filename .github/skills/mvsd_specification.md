# Minimal Viable Synthetic Dataset: BIS LBS Contract

Use this reference for fixture generation, approved metadata transfer and test
coverage. The client data authority approves the contract; the provider implements
it without confidential production observations.

## 1. Structure Identity

| Artifact | Reference |
| --- | --- |
| DSD | `BIS:BIS_LBS(1.0)` |
| Dataflow | `BIS:WS_LBS_D_PUB(1.0)` |
| XML | SDMx-ML 3.0 structure-specific data |
| Time dimension | `TIME_PERIOD` |
| Demonstration aggregation code | `LBSR` |
| Authority | [Pinned component/codelist snapshot](../../src/reference_data/lbs_structure.json), with source URL, digest and retrieval time |

Refresh the snapshot deliberately using [the refresh tool](../../sh/refresh_lbs_contract.py).
Runtime does not fetch unreviewed `latest` metadata. Public standards availability
does not imply redistribution rights; see [reference provenance](../../docs/reference_standards/README.md).

## 2. Ordered Dimensions and Measures

| Segment | Dimension | Role |
| --- | --- | --- |
| 1 | `FREQ` | Frequency; quarterly `Q` in this LBS fixture |
| 2 | `L_MEASURE` | Measure type |
| 3 | `L_POSITION` | Claims/liabilities |
| 4 | `L_INSTR` | Instrument |
| 5 | `L_DENOM` | Currency denomination |
| 6 | `L_CURR_TYPE` | Currency type |
| 7 | `L_PARENT_CTY` | Parent country |
| 8 | `L_REP_BANK_TYPE` | Reporting bank type |
| 9 | `L_REP_CTY` | Reporting country, checked by row filter and mask |
| 10 | `L_CP_SECTOR` | Counterparty sector |
| 11 | `L_CP_COUNTRY` | Counterparty country |

The pinned codelists define valid values; table examples and generic stress labels
are not alternative authorities. `OBS_VALUE` uses `DECIMAL(38,3)`; signed and
genuine zero observations are retained. Masked absence is not zero.

The explicit synthetic profile includes `DECIMALS=3`, `UNIT_MEASURE=USD`,
`UNIT_MULT=6`, `COLLECTION=E`, `AVAILABILITY=A` and frequency-derived `TIME_FORMAT`.
These attributes must be carried at their defined attachment levels. Three-place
precision is not a universal SDMx requirement, and `L_DENOM` does not convert units.

## 3. Educational Calculation Artifacts

The modeled international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions are included solely to demonstrate how realistic observations
and confidentiality flags are calculated. The generator and protected demo ledger
are not institutional intake requirements or system deliverables. Domestic granular
collections and other reporting regimes are outside this exchange contract.

The generator illustrates most-restrictive classification and a 0.60 dominance
threshold using absolute contributions. The receiving validator checks the SDMx
file independently; it does not recompute it from the ledger. This synthetic rule
does not establish complete disclosure control or an international mandate.

## 4. Required Coverage

| Case | Expected Evidence |
| --- | --- |
| Multiple jurisdictions, restricted values in more than one | Own/foreign row and measure isolation; additive-membership mask test |
| Public, researcher, submitter, administrator and no-group identities | Explicit public membership and fail-closed absence of entitlement |
| Genuine zero, negative, missing and masked values | Decimal fidelity and distinct value meanings |
| Valid aggregate/component rows | Arithmetic reconciliation actually evaluated |
| Structurally valid arithmetic failures | Whole-submission quarantine with precise observation and batch feedback |
| Malformed structure, codes, sender mapping and duplicates | Input refused before persistence |
| Same-period accepted replacement, including fewer keys | Atomic scope closure and one current accepted snapshot |
| Same-message replay and new identical filing | No duplicate replay; distinct new submission retained |
| Rejected and older accepted arrivals | Audit-only records do not displace current accepted data |
| Public-total and researcher-row reconstruction | Disclosure risk recorded, not falsely described as controlled by masking |

The baseline fixture contains CA4 + US4 + GB14 published observations, followed
by 22 quarantined revision observations. CA and US failures include `LBS_CC01`;
GB failures include `LBS_CC02` and `LBS_CC:04`. Additional acceptance tests cover
accepted replacements and replay; the rejected fixture alone does not prove expiry.

## 5. Analyst and Researcher Acceptance

The **Analyst View** must reconcile the latest filing expected by a regional
submitter with the receiver's actual IDs, submitted/received timestamps, values
and verdict. Latest submitted and current accepted publication remain distinct.
Full accepted history and trusted transport receipt are separate workflows.

Researcher discovery supports a later agreement request, not restricted-value
permission. Row presence, counts, keys and public totals can reveal withheld data.
Invite [synthetic community challenges](../../SECURITY.md#statistical-reconstruction-challenge)
and restrict/remove the role if existence makes reconstruction trivial.

## 6. pysdmx Integration

Use pinned `pysdmx[xml]==1.18.0`, the existing structure builders and serializers.
Do not duplicate a live-registry fallback recipe. DSD `Component.local_codes`
differs from registry-schema examples using `.codes`; use the actual installed
model. Dataset attributes belong in `PandasDataset(attributes=...)` where their
attachment level requires it. Structure-specific parsing alone does not verify
every DSD, codelist or provision-agreement constraint.

## 7. Client Transfer and Acceptance

Transfer only approved DSD/codelists, rules, disclosure-safe magnitude estimates,
policy expectations and generated fixtures. Exclude confidential observation values,
real institution identifiers, unpublished periods and exact confidential counts.
Generation from a seed is not evidence that sensitive metadata is harmless.

The provider returns reviewed code, fixture generators, tests, provenance, operating
documents and evidence. The client imports the approved version, configures its own
identities/state, accepts synthetic staging and approves production adaptation.
Do not run the demonstration generator as a production submission source.
See [Nature of Engagement and Handover](../../docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md).

## Related Skills

- [Persona contract](persona_security_matrix.md)
- [SDMx validation](sdmx_lbs_validation.md)
- [Submission history](scd2_engine.md)
- [Protected policy deployment](triple_lock_security.md)
- [Provider workflow](contractor_zero_trust_workflow.md)