# SovereignShield: Persona Demonstration

**Audience:** statistical leaders, data architects, reporting analysts and researchers.
**Format:** optional 3-5 minute technical follow-up after the publication launch.

The companion publication is **Bridging Public Dissemination and Protected Data:
A Zero-Trust SDMx Architecture on Azure Databricks**, available as an
[Executive Brief](EXECUTIVE_BRIEF.md) and [White Paper](whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md).
Follow [the publication plan](LINKEDIN_POST.md) for ordering and evidence links.

## Reference Captures

The current publication images are the synthetic captures supplied on 18 September
2026, copied without editing labels, values or filters. They replace the older
anonymized screenshots. The [capture inventory](../demo/README.md) records the
selected source/state mapping. These screenshots document displayed behavior,
not an independent authentication trace or the outcome of every acceptance test.

| Persona | Capture |
| --- | --- |
| Canadian Regional Submitter (CA), published | [Published view](../demo/submitter_ca_view.png) |
| Canadian Regional Submitter (CA), quarantine included | [All submissions view](../demo/submitter_ca_all_submissions.png) |
| US Regional Submitter (US), published | [Published view](../demo/submitter_us_view.png) |
| Anonymous public, 13 rows | [Public view](../demo/public_view.png) |
| Researcher, 22 rows and 9 masked measures | [Researcher view](../demo/researcher_view.png) |
| Researcher filtered to GB, 14 rows and 4 masked measures | [GB-filtered view](../demo/researcher_gb_view.png) |
| CA submitter, 4 rejected rows | [Quarantine-only view](../demo/submitter_ca_quarantine_view.png) |
| Administrator, 22 current published rows | [Published administrator view](../demo/admin_published_view.png) |

Label current recordings with date, tested revision, synthetic dataset and actual
hosting mode. A browser fixture is presentation evidence, not proof of live SSO.
No recording may show tokens, credentials, personal accounts or confidential records.

## Information Scope

The international exchange modeled here accepts **SDMx files only**. Synthetic
bank micro-transactions exist solely as educational artifacts illustrating how
realistic observations are calculated. The demo ledger is not an institutional
intake requirement or system deliverable. Domestic granular collection is outside
this workflow and should not appear as an international submission arrow.

The **Analyst View** is the regional submitter workflow. Its primary purpose is to
verify that the latest filing an analyst expects the international organization
to hold matches actual submission IDs, timestamps, values and validation outcomes.
Latest submitted, latest received and current accepted publication are distinct.

The **Researcher View** is conditional discovery, not guaranteed non-disclosure.
Public totals, dimensions and observation existence can reveal masked values.
Invite synthetic community challenges and restrict/remove the role if row presence
makes reconstruction trivial. An agreement request does not itself grant access.

## Demonstration Sequence

### 0:00-0:30: Scope and Public Result

**Screen:** public view with filters reset and the hosting mode identified.

**Narration:**

> SovereignShield is an independent synthetic reference architecture for SDMx
> submission governance. The receiving platform accepts SDMx files, validates
> submissions and separates current publication from rejected arrivals. Azure
> and Databricks implement the reference controls.

> The anonymous endpoint uses a dedicated public identity. This fixture returns
> thirteen current published observations explicitly classified free to publish.

### 0:30-1:05: Filters and Published Exports

**Screen:** select a reporting country, inspect the result and reset. Open one
SDMx export and identify the selected scope and units.

**Narration:**

> The gateway selects identity, lifecycle and user filters. Unity Catalog enforces
> row and value entitlements on the governed query. Standard SDMx products contain
> current accepted data only; masked absence is not a zero measurement.

> The gateway handles tokens and entitled results and remains a trusted component.

### 1:05-1:45: Researcher Discovery and Open Risk

**Screen:** researcher fixture with 22 published rows and nine masked measures.

**Narration:**

> Researcher discovery identifies a published series and its originating authority
> while withholding restricted measures. Obtaining those values requires a separate
> agreement and approved entitlement.

> The existence of a row is itself information. Published totals and known calculation
> relationships can reconstruct a hidden component. This is an open challenge:
> restrict or remove researcher discovery if row presence makes inference trivial.
> Public-only releases also require statistical disclosure review.

**Evidence boundary:** show synthetic reconstruction examples only. No live attack
or third-party probing is part of this demonstration.

### 1:45-2:50: Analyst Reconciliation

**Screen:** CA submitter, then US submitter. In CA, select Published + quarantine,
then Quarantine only. Identify a submission ID, timestamps and failure feedback.

**Narration:**

> Analysts can verify that the latest filing they expect the international
> organization to hold is actually present, with the expected identity, values
> and outcome. Each submitter sees its own restricted data and public foreign data.

> A later rejected filing remains visible for diagnosis but does not replace the
> prior accepted publication. Observation-level failures and the batch rejection
> reason support reconciliation between sender and receiver.

> The portal distinguishes current publication and rejected arrivals. Complete
> accepted history requires an authorized history query; processing timestamps
> are not an independently attested transport receipt.

**Expected fixture:** CA has 14 current published rows and 18 with quarantine;
US has 17 current published rows and 21 with quarantine. Counts depend on this
fixture and should not be reused as production claims.

### 2:50-3:30: Administrator Oversight

**Screen:** administrator in Published mode, then Published + quarantine.

The supplied administrator screenshot shows Published mode only. A live authorized
recording or an additional capture is required to illustrate the 44-row audit mode;
do not relabel the 22-row screenshot as that view.

**Narration:**

> The administrator sees 22 published rows or 44 rows including rejected revisions
> in this fixture. Accepted and rejected records remain distinct. A smaller accepted
> replacement closes omitted keys in one country/period/aggregation transaction;
> rejected arrivals leave current accepted data unchanged.

### 3:30-4:15: Delivery and Operating Model

**Screen:** current [architecture diagrams](ARCHITECTURE_DIAGRAMS.md) and the
[engagement workflow](ENTERPRISE_ONBOARDING_PLAYBOOK.md#engagement-workflow).

**Narration:**

> The external provider develops against an approved synthetic contract. The client
> owns production records, deployment identities, release approval and operations.
> Repository handover, staging acceptance and production approval are separate steps.

> The core pattern is technology-agnostic. Terraform supports AWS, GCP, Fabric and
> open-source adaptations, but equivalent identity, policy and history controls
> require implementation and testing.

### 4:15-4:45: Evidence and Invitation

**Narration:**

> Live provisioning and teardown completed successfully. The synthetic reference
> cycle measured about seventy-five minutes up including prerequisites, thirty
> minutes down and ten US dollars or less in Azure charges for deployment, testing
> and teardown. Those are observed evaluation results, not production guarantees.

> Technical feedback is invited on analyst reconciliation, institutional handover
> and reconstruction from public values or researcher-visible rows. The repository
> includes the evidence, limitations and security reporting route. No institutional
> or vendor endorsement is implied.

## Implemented and Proposed Workflows

| Implemented in the Reference | Requires Additional Design or Acceptance |
| --- | --- |
| Public and signed-in persona paths, row/value entitlements | Institution-specific SSO, network and operating acceptance |
| Published/all/quarantine views, IDs, timestamps and failure feedback | Trusted transport receipts, full latest-arrival dashboard and bilateral case management |
| Current SDMx exports and submission-aware audit CSV | Researcher accreditation, agreements, expiry and purpose-limited approval workflows |
| Immutable replay and accepted/rejected history | Distributed conflict handling and production-volume recovery evidence |
| Researcher masking and structural discovery | Secondary suppression or another approved statistical disclosure-control product |

Use the [release evidence](RELEASE_EVIDENCE.md) for dated results and measurement
scope. The brief leads the LinkedIn launch; the full White Paper provides depth.
A video is supporting material, not a prerequisite or a guaranteed reach multiplier.