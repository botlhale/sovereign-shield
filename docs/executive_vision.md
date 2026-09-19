# Executive Vision: Strategic Business Case

**Audience:** sponsors, procurement, senior leadership and architecture boards.
**Affiliation:** independent reference architecture; no institutional or vendor endorsement.

The decision publications are **Bridging Public Dissemination and Protected Data:
A Zero-Trust SDMx Architecture on Azure Databricks**, available as an
[Executive Brief](EXECUTIVE_BRIEF.md) and [White Paper](whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md).
This document summarizes the investment and operating rationale.

## Business Objective

Synthetic-first delivery enables external specialists to develop statistical
platform controls without confidential production records. Client-controlled
runtime identities and repositories support continuity after the engagement.
The pattern complements established SDMx software and institutional governance;
it does not replace disclosure decisions, independent assurance or production operations.

| Decision Area | Reference Approach | Client Acceptance |
| --- | --- | --- |
| Specialist delivery | Approved metadata and generated fixtures | Contract, IP/license review, access scope and deliverable ownership |
| Trust in current data | Analyst reconciliation of expected latest filing with receiver state | Submission/receipt semantics and current accepted-publication rules |
| Public and restricted use | Query-time entitlements and distinct publication/audit products | Disclosure control, including reconstruction from public values |
| Operating continuity | Stable client-owned service principals and ownership review | Operator-led handover, recovery and complete offboarding |
| Platform choice | Technology-agnostic information/delivery pattern, implemented on Azure/Databricks | Equivalent controls and adapters for any alternative stack |

## Scope of the Demonstration

The modeled international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions are educational artifacts explaining how realistic observations
are calculated. The demo ledger is not a system deliverable or a requirement for
an institution to transmit granular records. Domestic reporting arrangements are
outside this contract.

The **Analyst View** gives regional submitters a basis for verifying that the latest
filing they expect the international organization to hold matches actual submission
identities, timestamps, values and validation feedback. A rejected latest filing
does not replace the current accepted publication.

## Information Risk

The Researcher role exposes published structure while withholding restricted
measures. Observation existence, public totals, related breakdowns and revisions
may make masked data reconstructable. This is an identified open challenge, not
a completed confidentiality guarantee. Synthetic community review is invited;
restrict or remove the role if row presence makes reconstruction trivial. Public
releases also require an approved disclosure-control method.

Logical jurisdictional segregation in a shared workspace is not physical country
residency. Privileged operators, gateway tokens, archives and downloaded products
remain trust boundaries. Full offboarding is an identity, access and ownership
review, not group removal alone.

## Evaluation Economics

Provisioning and teardown have completed successfully on Azure. The reference
synthetic cycle measured approximately **75 minutes for bring-up including
prerequisites**, **30 minutes for teardown**, and **US$10 or less in Azure charges
for deployment, testing and teardown**. See [measurement provenance](RELEASE_EVIDENCE.md#reference-evaluation-metrics).

This supports a low-cost bounded evaluation. It does not include a consulting-fee
estimate, production SLA, savings percentage or recurring production cost model.
Scale, region, subscription pricing, idle resources, logs and retained artifacts
must be budgeted separately for adoption.

## Adoption Options

Retain existing SDMx infrastructure, extend it, or pilot this implementation based
on the institution's interoperability, residency, ownership and operating needs.
Terraform provider/module boundaries support AWS, GCP, Microsoft Fabric and
open-source combinations, but identity, policy, storage and lifecycle adapters
require engineering and equivalent acceptance. No alternate stack is represented
as already deployed.

The [Nature of Engagement and Handover](ENTERPRISE_ONBOARDING_PLAYBOOK.md) defines
client prerequisites, independent-versus-client repository options, synthetic
staging, production approval, code transfer and provider offboarding. A repository
clone is a transfer mechanism; production acceptance remains a client decision.