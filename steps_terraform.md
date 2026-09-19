# Terraform Deployment and Recovery Reference

Terraform is the reference infrastructure owner. The supported end-to-end
entry points are [sovereignshield_up.ps1](sh/sovereignshield_up.ps1) and
[sovereignshield_down.ps1](sh/sovereignshield_down.ps1). They coordinate Terraform,
Databricks account setup, bundle resources, data/policies and the two portal hosts.
The [operations runbook](docs/AUTOMATION_RUNBOOK.md) is the canonical sequence;
this document identifies prerequisites, ownership and safe recovery decisions.

## Scope and Evaluation

The modeled international exchange accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely as educational artifacts showing the calculation
of realistic observations and classification flags. The demo ledger is not an
institutional intake requirement or system deliverable. Domestic granular-data
collections are outside this contract.

Successful reference bring-up took approximately **75 minutes including prerequisite
setup**; teardown took another **30 minutes**. The deploy/test/teardown cycle cost
**US$10 or less in Azure charges**. These are observed synthetic-workload figures,
not production pricing or duration guarantees. See [measurement scope](docs/RELEASE_EVIDENCE.md#reference-evaluation-metrics).

The core information/delivery framework is technology-agnostic. Terraform supports
AWS, GCP, Microsoft Fabric and open-source provider/module adaptations, but identity,
storage, policy and transactional-history adapters require equivalent acceptance.
The repository implements Azure and Databricks; it does not deploy every alternative.

## Prerequisites

- Approved scope, budget, region, quota, network/residency requirements and client owners.
- Azure CLI, Databricks CLI, Terraform, Git and the selected Python environment.
- An authorized Azure subscription/tenant and Databricks account with the required
  regional Unity Catalog metastore arrangement.
- Client-authorized administrators for scoped resource/RBAC operations, Entra
  identity/consent operations, Databricks account membership and runtime-use grants.
- Existing human persona accounts; the scripts do not create users or collect passwords.
- A pre-created, secured remote Terraform state backend and non-secret local
  configuration based on [backend.hcl.example](terraform/backend.hcl.example) and
  [terraform.tfvars.example](terraform/terraform.tfvars.example).
- Required repository/environment review gates for any privileged CI promotion.

State, saved plans, runtime credentials and authentication session storage are
sensitive even when configuration contains no credential literals. Do not copy
provider state or tokens into a client production environment. Review
[the engagement prerequisites](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md#2-client-prerequisites-and-access).

## Fresh or State-Aware Bring-Up

Run from the repository root, using approved subscription and account identifiers:

```powershell
az login --tenant "<tenant-guid>"
az account set --subscription "<subscription-guid>"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force
.\sh\sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>"
```

`az login` establishes Azure authentication; it does not supply the mandatory
Databricks account GUID or tenant-domain script parameter. Local execution policy
changes are process-scoped. Do not elevate or change machine-wide policy merely
to run the reference.

`-DeploymentMode Auto` reads state-derived readiness. Foundation and later grant
applies preserve established flags. Unique plans are inspected for destructive
changes; unexpected failures stop the run. `SteadyState` requires completed
bootstrap. A checkout lifecycle lock prevents overlapping local `up`/`down`
operations; one authorized controller is still required across machines.

## Ordered Ownership

| Stage | Owner and Result |
| --- | --- |
| 0 | Preflight: tools, providers, config, existing users and offline tests |
| 1 | Terraform foundation, namespaces, storage, vault, compute policy and warehouse |
| 2 | Databricks account identities/assignments and subsequent Terraform traversal grants |
| 3 | Exact runtime-use permission, bundle validation and resource/source deployment |
| 4 | Four job tasks: protected DDL, synthetic generation, validated history ingestion, live runtime acceptance |
| 5 | Terraform table grants after protected objects exist |
| 6 | Managed public membership, bundle-resolved App source, bounded exact-deployment activation |
| 7 | Script-owned gateway build/deployment and optional Easy Auth, unless Terraform owns the gateway |
| 8 | App state, group SQL access, anonymous fixture and configured Easy Auth checks |

Terraform owns grants; bundle/SQL execution owns data and policy bindings. The
optional Terraform gateway and script gateway are alternative owners, not two
writers for the same resource. The repository uses script-owned account setup;
this is not a claim that the Databricks Terraform provider lacks account APIs.

Complex cluster variables use ignored target-specific bundle override JSON.
Do not put a complex cluster object into `BUNDLE_VAR_ingestion_cluster`. The
single-node/no-Photon defaults and stable runtime identity are preserved; larger
compute requires explicit approval and runtime acceptance.

## Resume a Partial Run

Use the last failed stage, not a teardown, when earlier stages completed:

```powershell
.\sh\sovereignshield_up.ps1 `
  -AccountId "<databricks-account-guid>" `
  -TenantDomain "<tenant-domain>" `
  -StartAtStage 6
```

| Failure | Recovery |
| --- | --- |
| Stage 3 run-as grant not immediately visible | Bounded same-ETag verification; resume at Stage 3 after checking account authorization |
| Stage 6 new App has no default source path | Resolve uploaded source from the selected bundle; resume at Stage 6, not Stage 3 |
| Stage 6 deployment wait timed out | Reconcile the exact pending/latest deployment; do not submit another copy |
| Completed generation followed by failed ingestion | Repair failed job tasks against immutable archived arrivals; do not generate new filings solely to replay |
| Failed ACR build/push | Stop before image rollout; use the existing registry and a verified image tag through the gateway helper |
| Legacy incompatible history or bundle ownership | Follow the explicit migration gate; do not force a routine apply |

`-StopAfterStage` bounds a run. `-AppTimeoutMinutes` bounds compute/deployment
waits. A failed/cancelled deployment remains a failure. Resource convergence and
same-message replay are idempotent; a new synthetic generator run creates new
submission identities and is not the same operation.

## Acceptance and Analyst Reconciliation

Stage 8 is a readiness check, not complete human SSO or statistical disclosure
acceptance. Record live signed-in personas, no-group denial, source/current-key
integrity, replay, rejection feedback, recovery and policy-binding evidence.

The **Analyst View** reconciles expected latest filings with actual receiver IDs,
timestamps, values and outcomes. Latest submitted data is not always the current
accepted publication. Researcher-visible row existence and public totals can
reconstruct withheld values. Use the [synthetic challenge](SECURITY.md#statistical-reconstruction-challenge)
and restrict/remove the Researcher role if existence makes inference trivial;
public releases need disclosure control independently.

## Pause and Workload Teardown

```powershell
.\sh\sovereignshield_down.ps1 -Mode Pause
.\sh\sovereignshield_down.ps1 -Mode Workload -WhatIf
```

Execute destruction only after approval of the preview:

```powershell
.\sh\sovereignshield_down.ps1 -Mode Workload -ConfirmWorkloadDestruction
```

Pause makes serving compute eligible to scale down; traffic can keep it running,
and retained resources remain billable. It is not a zero-cost guarantee.
The ordered workload teardown removes bound data/policy objects, bundle resources,
the owning gateway and Terraform workload, then verifies cleanup. Do not substitute
an isolated `terraform destroy` for this dependency-aware sequence.

The backend, Databricks account records, human Entra users and purge-protected
vault tombstone follow explicit retention rules. Script-owned Entra login
registrations and historical identity artifacts need separate inventory. An empty
workload resource group does not establish complete identity decommissioning.

## Client Handover

Follow [Nature of Engagement and Handover](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md):
approved source transfer, client-owned state/identities, synthetic staging,
production/disclosure approval, operator training and complete offboarding.
Cloning source does not make the synthetic generator a production intake source.
Legacy history requires [migration acceptance](docs/RELEASE_EVIDENCE.md#mandatory-migration-gate).

For resource-level decisions use [Resource Provenance](docs/RESOURCE_PROVENANCE.md).
For standalone helper boundaries use [the script reference](steps_scripts.md).