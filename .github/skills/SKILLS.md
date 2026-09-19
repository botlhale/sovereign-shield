# SovereignShield Architecture Reference Index

These repository reference notes define current implementation contracts for
contributors and reviewers. The owning source and tests take precedence over
historical diagrams or deployment recipes. A documented design option is not
an implemented feature or a substitute for institutional acceptance.

## Reference Notes

| Note | Responsibility | Use When |
| --- | --- | --- |
| [Synthetic information contract](mvsd_specification.md) | Pinned dimensions, metadata, generated fixtures and required cases | Changing data structures, synthetic fixtures or transfer scope |
| [Persona matrix](persona_security_matrix.md) | Account-group entitlements, analyst reconciliation and disclosure boundaries | Changing access, lifecycle selection or personas |
| [Policy deployment](triple_lock_security.md) | Protected DDL, immutable functions and ownership | Changing policies, bindings or runtime configuration |
| [SDMx validation](sdmx_lbs_validation.md) | Format, component/code and arithmetic validation | Changing rule interpretation or serialization |
| [Submission history](scd2_engine.md) | Immutable filing identity, replay and atomic full replacements | Changing persistence, ordering or audit semantics |
| [External-provider workflow](contractor_zero_trust_workflow.md) | Synthetic development, reviewed promotion, handover and offboarding | Onboarding contributors or reviewing delivery access |

## Information Boundaries

The modeled international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely as educational artifacts showing how realistic
observations and confidentiality flags are calculated. The demo ledger is not an
institutional intake requirement or system deliverable. Domestic granular-data
collections and other reporting regimes are outside this exchange contract.

The **Analyst View** is the regional submitter workflow: reconcile expected latest
filings with actual receiver identities, timestamps, values and validation outcomes.
Latest submission is not necessarily current accepted publication.

Researcher-visible row presence and public values can enable reconstruction.
Invite synthetic challenges under the [security policy](../../SECURITY.md#statistical-reconstruction-challenge).
Restrict or remove the Researcher role if observation existence makes inference
trivial; public-only data still needs disclosure review. Do not change runtime
permissions solely because a documentation review identifies this open decision.

## Implemented Capabilities

| Capability | Owning Implementation | Verification Boundary |
| --- | --- | --- |
| Pinned BIS LBS 1.0 structure and codelists | [lbs_contract.py](../../src/lbs_contract.py) | Deliberate refresh, not unreviewed live `latest` |
| Three-place exact measures, genuine zero retained | [decimal_measures.py](../../src/decimal_measures.py) | Reference profile, not universal SDMx precision |
| 21 within-dataset arithmetic rules | [sdmx_rule_validator.py](../../src/sdmx_rule_validator.py) | Six cross-collection checks unsupported; missing breakdowns reported |
| Account-group RLS and explicit-F decimal masking | [policy SQL](../../src/unity_catalog_triple_lock.sql) | Supported UC paths; not physical residency or disclosure control |
| No-detach policy deployment | [apply_security.py](../../src/apply_security.py) | Definition/binding verification; no multi-object atomic migration |
| One Delta MERGE per full submission | [Spark history adapter](../../src/spark_submission_history.py) | Single-writer job; separate ledger/history transactions |
| Same-message replay and new-identical-filing retention | [submission_history.py](../../src/submission_history.py) | Submission identity and digest, not payload hash alone |
| Current SDMx products and separate audit CSV | [api_gateway.py](../../src/api_gateway.py) | Trusted gateway; standard feeds exclude rejected/superseded rows |
| Protected manual cloud promotion | [promote.yml](../workflows/promote.yml) | PR verification has no cloud credentials; client configures reviewer gates |
| Resumable lifecycle | [up orchestrator](../../sh/sovereignshield_up.ps1) | Current Terraform outputs; bounded exact-ID App recovery |

Open `VALID_TO` is `NULL`; measures are `DECIMAL(38,3)`. Do not reintroduce
sequential expiry/append/delete transactions, floating-point measures, zero
suppression, detached policies, unvalidated export fallbacks or automatic human
ownership-transfer claims.

## Deployment and Portability

The core information/delivery framework is technology-agnostic; Azure and
Databricks are the demonstrated implementation. Terraform provider/module
boundaries support AWS, GCP, Microsoft Fabric and open-source adaptations.
Identity, storage, policy, history and hosting adapters require equivalent tests.

The successful synthetic reference cycle measured approximately **75 minutes up
including prerequisites**, **30 minutes down**, and **US$10 or less in Azure charges
for deploy/test/teardown**. Use [the measurement scope](../../docs/RELEASE_EVIDENCE.md#reference-evaluation-metrics),
not these values as production cost or duration guarantees.

The [engagement playbook](../../docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md) is authoritative
for client/provider responsibilities. The [operations runbook](../../docs/AUTOMATION_RUNBOOK.md)
owns commands, recovery and resource retention.