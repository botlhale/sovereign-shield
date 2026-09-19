# Technical Guide: Repository Reading Order

This guide supports code and architecture review. Deployment commands, stage
recovery and teardown belong to the [operations runbook](AUTOMATION_RUNBOOK.md).
Local tests require no cloud credentials; live identity and engine checks require
an authorized synthetic workspace.

## Before You Start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest tests/
```

Record the commit and environment with test results. Opt-in `live` and `stress`
skips are not passes. The local policy mirror is a development tool, not a security
boundary against someone who can read local files.

## Pass 1: Architecture and Evidence

Read [README](../README.md), [technical vision](technical_vision.md) and
[architecture diagrams](ARCHITECTURE_DIAGRAMS.md). The companion Executive Brief
and White Paper have the shared title **Bridging Public Dissemination and Protected
Data: A Zero-Trust SDMx Architecture on Azure Databricks**.

Identify four separate concerns: information contracts, infrastructure ownership,
query-time entitlements and statistical disclosure. A table policy does not
eliminate application, gateway, storage or operator trust.

Live provisioning and teardown succeeded. The synthetic evaluation measured
approximately **75 minutes up including prerequisites**, **30 minutes down**, and
**US$10 or less in Azure charges for deploy/test/teardown**. Read the
[measurement boundaries](RELEASE_EVIDENCE.md#reference-evaluation-metrics) before
using those values in an institutional business case.

## Pass 2: Information Contract

Read [the MVSD contract](../.github/skills/mvsd_specification.md),
[lbs_contract.py](../src/lbs_contract.py), and
[generate_sovereign_submissions.py](../src/generate_sovereign_submissions.py).

The international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely as educational artifacts showing how realistic
observations are calculated. Their demo ledger is not an institutional intake
requirement or system deliverable. The receiver validates the submitted file
independently; it does not recompute it from the educational ledger.

The eleven-part key uses segment 9 for reporting country and segment 1 for frequency.
The LBS fixture is quarterly; generic multi-cadence stress labels are not evidence
of valid BIS codes. The pinned structure/codelists and explicit metadata profile
are authoritative. `DECIMAL(38,3)`, genuine zero and masked absence have distinct
semantics; three decimals are a reference convention, not universal SDMx policy.

## Pass 3: Security Core

Read in order:

1. [Policy SQL](../src/unity_catalog_triple_lock.sql): independent `OR` entitlements,
   segment-9 ownership checks, explicit public membership and fail-closed masking.
2. [Policy executor](../src/apply_security.py): schema checks, immutable functions,
   no-detach binding changes, definition/binding verification and error propagation.
3. [Persona reference](../.github/skills/persona_security_matrix.md): account-group
   resolution, temporal product scope and trusted boundaries.
4. [Local query mirror](../src/uc_query.py) and [persona tests](../tests/test_persona_access_matrix.py):
   compare expectations with the actual UC policy, not merely with each other.

The mask repeats own-country validation even when the row filter permits access
through another membership. Unknown/missing classification is withheld except
for explicitly entitled administrator/own-country access. Non-throwing segment
lookup prevents indexing failures; strict ingestion still owns key validation.

The Researcher role reveals observation presence. Public totals and related
breakdowns can reconstruct a masked value without a policy bypass. Follow the
[open synthetic challenge](../SECURITY.md#statistical-reconstruction-challenge)
and restrict/remove that role if existence disclosure makes inference trivial.
Public products require independent disclosure review as well.

## Pass 4: Validation and History

Read [sdmx_rule_validator.py](../src/sdmx_rule_validator.py),
[submission_history.py](../src/submission_history.py),
[spark_submission_history.py](../src/spark_submission_history.py),
[scd2_merge_engine.py](../src/scd2_merge_engine.py) and
[local_pandas_scd2.py](../src/local_pandas_scd2.py).

Format, DSD/code, sender/profile and arithmetic checks are distinct. Twenty-one
within-dataset checks are implemented; six cross-collection checks and missing
breakdowns are explicitly reported. The workbook interpreter remains code requiring
semantic review. Metadata changes need regression tests.

One immutable message contains a full country/period/aggregation snapshot. Accepted
expiry and insertion occur in one Delta MERGE. A smaller replacement closes omitted
keys only in that scope. Rejected or late audit-only arrivals do not close the
current accepted state. Same-message replay is a no-op; a new identical filing
retains identity. Current `VALID_TO` is `NULL`, and temporal columns are uppercase
in the current local and Spark contracts.

The job is single-writer. The local file lock does not coordinate distributed
writers, and the ledger/history writes are not a multi-table transaction. Repair
against archived files; generator reruns produce new message identities.

## Pass 5: Analyst and Dissemination Products

Read [api_gateway.py](../src/api_gateway.py), [uc_query.py](../src/uc_query.py),
[sdmx_ml_exporter.py](../src/sdmx_ml_exporter.py) and
[lifecycle tests](../tests/test_lifecycle_api.py).

The **Analyst View** reconciles the latest filing a submitter expects the
international organization to hold with actual IDs, timestamps, values and verdicts.
`lifecycle=published|all|quarantine` distinguishes current publication from rejected
arrivals. Complete accepted history and trusted transport receipts remain separate
workflows; processing time is not transport attestation.

The trusted gateway selects identity, lifecycle and user filters; UC applies row/value
entitlement. Standard SDMx exports are current/published-only; audit CSV is separate.
The serializer uses pinned offline components and exact decimal formatting.
Masked values are absent, never zero. Exported files cannot enforce future revocation.

## Pass 6: Infrastructure and Ownership

Read [the engagement playbook](ENTERPRISE_ONBOARDING_PLAYBOOK.md),
[Terraform root](../terraform/main.tf), [compute policy](../terraform/modules/databricks_workspace/compute.tf),
[governance grants](../terraform/modules/unity_catalog_governance/main.tf) and
[resource provenance](RESOURCE_PROVENANCE.md).

Terraform owns infrastructure and grants. The bundle and policy executor own
data/policy objects without detaching existing protection. One owner manages each
grant principal/securable pair. Databricks account setup, run-as permission and
stable object ownership are separate operations.

The framework is technology-agnostic; Terraform provider/module boundaries support
AWS, GCP, Microsoft Fabric and open-source adaptations. Azure authentication,
Databricks hosting and UC SQL are implementation-specific. Ports need equivalent
identity, policy, history and recovery tests.

### Pass 6a: Compute Sizing

The reference defaults to a single-node, no-Photon ingestion policy and an
independently auto-stopping SQL warehouse. Larger workers or Photon require
`-ApproveComputeScale`. Runtime/access-mode policy support must be checked; do not
describe every dedicated compute mode as an unfiltered bypass.

More workers do not distribute pandas XML parsing and arithmetic validation or
automatically parallelize jurisdictions. Measure driver memory, merge cost,
individual query latency, queueing and total resource usage before resizing.
Warehouse size and concurrency are different levers, and neither is a universal fix.

### Pass 6b: Scale and Stress Tests

```powershell
.venv\Scripts\python.exe src/generate_stress_test_data.py --rows 100000 --frequencies "A,S,Q,M" --periods 4
.venv\Scripts\python.exe -m pytest tests/test_scale_and_stress.py --stress
```

The [stress generator](../src/generate_stress_test_data.py) and
[stress tests](../tests/test_scale_and_stress.py) measure synthetic local behavior.
The optional synthetic micro fixture is educational, not a submitted production
ledger. Record seed, actual corpus counts, hardware and test selection; do not
present laptop linearity as concurrent cloud throughput.

Spark tests require a compatible JVM. `JAVA_GATEWAY_EXITED` can prevent session
construction; an environment skip does not validate a merge. Failures after a
session starts must not be hidden as environmental skips.

## Pass 7: Provider Engagement and Handover

Read [the provider workflow](../.github/skills/contractor_zero_trust_workflow.md),
[the client playbook](ENTERPRISE_ONBOARDING_PLAYBOOK.md) and
[the promotion workflow](../.github/workflows/promote.yml).

Review approved independent-versus-client repository ownership, confidential
metadata boundaries, time-bounded sandbox access, independent promotion and
client-run production acceptance. A clone does not deploy or certify production.
Offboarding includes identities, sessions, RBAC, vault, GitHub, ownership and
exports while retaining client-owned runtime service principals.

## Pass 8: Focused Failure Injection

Use a disposable local copy with synthetic data and no cloud credentials. Introduce
one deliberate mask defect, such as removing the segment-9 ownership check, and
run [persona tests](../tests/test_persona_access_matrix.py). The dual-membership
test must detect foreign-value exposure; the exact number of failures can change
as coverage grows. Revert only the deliberate edit or discard that isolated copy,
not unrelated work in the primary checkout.

Repeat with single-country versus multi-country fixtures to assess coverage gaps.
A test that only observes rows already removed by RLS does not verify the mask.
Then construct a synthetic inference case from public totals and row presence:
correct authorization can coexist with unacceptable information disclosure.

## Review Outputs

Record the tested revision, contracts verified, commands/results, skipped gates,
information risks and named client decisions. Use [Release Evidence](RELEASE_EVIDENCE.md)
for migration and measurement limits and [the publication plan](LINKEDIN_POST.md)
for stakeholder distribution. Do not equate a reference evaluation with production
accreditation, physical residency or universal revocation.