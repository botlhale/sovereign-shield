# Technical Vision: Information Products and Enforcement

**Audience:** enterprise data/information architects, security reviewers and platform engineers.
See [implementation detail](technical_reference.md), [architecture diagrams](ARCHITECTURE_DIAGRAMS.md)
and [the strategic case](executive_vision.md).

## Design Intent

The framework separates the information contract, infrastructure ownership,
data/policy execution and published/audit consumption. Its principles are
technology-agnostic; Azure and Databricks are the demonstrated implementation.
Terraform supports provider/module adaptations for AWS, GCP, Microsoft Fabric
and open-source combinations. Identity, transactional history, query policy and
hosting controls must be reimplemented and acceptance-tested for each port.

## Submission Boundary

The modeled international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely as educational artifacts illustrating the
calculation of realistic observations and confidentiality flags. Their protected
demo ledger is not an institutional intake interface or system deliverable.
Domestic granular-data collections are outside this exchange contract.

The receiving validator checks the submitted observations rather than recomputing
them from the educational ledger. That distinction preserves sender accountability
and independent receiver validation.

## The Series Key

The pinned BIS LBS 1.0 contract defines eleven ordered dimensions:

```text
FREQ.L_MEASURE.L_POSITION.L_INSTR.L_DENOM.L_CURR_TYPE.L_PARENT_CTY.L_REP_BANK_TYPE.L_REP_CTY.L_CP_SECTOR.L_CP_COUNTRY
```

Segment 9 is `L_REP_CTY`, the reporting jurisdiction. Both the row filter and mask
check it for own-country access. Group memberships combine additively, while a
submitter's membership does not unmask foreign restricted values.

Strict ingestion validates canonical keys and codelists. Non-throwing SQL segment
lookup prevents indexing errors; it does not prove every malformed key is invisible
through all policy branches. Administrators remain privileged.

## The History Table

| Field | Information Meaning |
| --- | --- |
| `TIME_SERIES_CODE`, `DATE`, `AGG_CODE` | Observation key and country/period/aggregation replacement scope |
| `OBS_VALUE` | `DECIMAL(38,3)`; signed values and genuine zero retained |
| `OBS_STATUS`, `OBS_CONF` | Observation status and sender-owned confidentiality classification |
| `QUALITY_STATUS`, `BATCH_STATUS` | Implemented validation result and publication/quarantine state |
| `FAILED_RULE_ID`, `BATCH_FAILED_RULE_ID`, `VALIDATION_NOTES` | Observation-specific feedback, batch reason and evaluated/unsupported coverage |
| `SUBMISSION_ID`, `SOURCE_SHA256`, `RECORD_ID` | Immutable filing identity, source evidence and submission-aware row identity |
| `SUBMITTED_AT`, `RECEIVED_AT` | Sender-reported time and receiver processing time |
| `VALID_FROM`, `VALID_TO`, `IS_CURRENT` | History interval; open current `VALID_TO` is `NULL` |

An accepted newer full snapshot closes all current records in the same scope and
inserts the replacement in one Delta MERGE, including keys omitted by a smaller
replacement. A rejected or older accepted arrival is retained audit-only. Replaying
one immutable message is a no-op; a new identical filing is a distinct event.
Macro and educational-ledger writes are separate transactions.

## Analyst View and Data Currency

The **Analyst View** is the regional submitter workflow. Analysts verify that the
latest submission they expect the international organization to hold matches the
actual filing identity, timestamps, values and validation outcome. Current accepted
publication is not synonymous with latest submitted or latest received data.

The portal offers `lifecycle=published|all|quarantine`: current published data,
current publication plus rejected arrivals, or rejected arrivals only. Full accepted
history remains an authorized history-query workflow. The implementation does not
provide an independently attested transport receipt or universal latest-arrival
dashboard. Production must agree trusted sequencing and receipt semantics.

## Entitlement and Disclosure

Unity Catalog evaluates Databricks account-group membership on supported query
paths. Setup reconciles selected Entra identities, not continuous directory
deprovisioning. Administrator and own-country entitlements reveal values; otherwise
only explicit `F` is revealed, including fail-closed treatment of unknown flags.

The public proxy receives published free rows. Researchers can discover published
structure with restricted measures masked. That discovery supports an agreement
request to the originating authority, not access to the value.

Published totals, overlapping breakdowns and observation existence can reconstruct
restricted values. The [open reconstruction challenge](../SECURITY.md#statistical-reconstruction-challenge)
invites synthetic community tests. Restrict or remove the Researcher role when
row presence makes inference trivial. Public-only releases still need disclosure
control; neither masking nor the synthetic dominance rule establishes that control.

## Gateway and Information Products

The gateway selects identity, user filters and lifecycle scope. UC applies row/value
entitlements. The gateway is trusted because it handles credentials, bearer tokens
and entitled results. It is not secure under arbitrary compromise.

| Consumer | Identity and Product |
| --- | --- |
| Workspace user | Databricks App SSO and forwarded caller SQL token |
| Signed-in Container Apps user | Easy Auth and a caller token forwarded to the API |
| Anonymous Container Apps visitor | Dedicated public-proxy principal with explicit public membership |
| Standard SDMx consumer | Current published SDMx-ML 3.0, SDMx-JSON 2.0 or SDMx-CSV 2.0 |
| Entitled analyst/auditor | Submission-aware audit CSV and authorized history query |

Pinned offline structure components support serialization; normal exports do not
depend on an unreviewed live registry or silently use an unvalidated fallback.
Three-place formatting is a reference profile. Masked absence is never zero.

## Ownership and Acceptance

Terraform owns infrastructure and grants; bundle jobs and the policy executor own
table DDL and protected policy bindings. Immutable content-addressed functions
avoid policy detachment during normal deployment. Each grant principal/securable
pair has one writer. Stable client-owned runtime identities do not automatically
transfer existing table ownership or revoke human privileges.

Offboarding includes groups, sessions/tokens, Azure RBAC, vault, GitHub, delegated
ownership and exports. The [engagement playbook](ENTERPRISE_ONBOARDING_PLAYBOOK.md)
defines the client-controlled transfer and approval sequence.

Successful synthetic provisioning and teardown measured approximately **75 minutes
up including prerequisites**, **30 minutes down**, and **US$10 or less in Azure
charges for deploy/test/teardown**. See [measurement scope](RELEASE_EVIDENCE.md#reference-evaluation-metrics).
Production residency, disclosure, migration, recovery, throughput and recurring cost
remain institution-specific acceptance gates.