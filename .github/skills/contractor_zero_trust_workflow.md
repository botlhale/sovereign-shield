# External Technical Provider Delivery Workflow

Use this reference for contributor access, synthetic development, promotion and
handover. The [Nature of Engagement and Handover](../../docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md)
defines the client-facing contract and acceptance sequence.

## Trust and Ownership Boundaries

| Boundary | Approved Flow | Required Owner |
| --- | --- | --- |
| Specification | Reviewed DSD, codes, rules, persona matrix and disclosure-safe metadata | Client data authority |
| Development | Independently generated fixtures, code and credential-free tests | Provider within approved repository/workstation policy |
| Live evaluation | Time-bounded access to a segregated synthetic sandbox where authorized | Client platform/security owner |
| Promotion | Reviewed artifacts through explicitly approved identities/environments | Client independent reviewer and operator |
| Production | Confidential records and SDMx intake inside client systems | Client data authority and operations |

The client may approve a provider-controlled independent repository for reusable
synthetic work, or require a client-controlled repository from inception. A client
repository is not an employer repository unless that employer is the contracted
client. No employer code, credentials, equipment or data is implicitly authorized.

Synthetic generation must not leak production-derived distributions, exact counts
or identifiers through metadata. The international intake is SDMx files only;
synthetic bank micro-transactions are educational calculation fixtures, not a
client data-delivery requirement or production system deliverable.

## Local Development

Use the [MVSD contract](mvsd_specification.md), pinned structure and existing
dependency manifests. The local pandas/delta-rs backend mirrors selected policy
and history expectations without cloud credentials; it does not prove live
identity enforcement, distributed conflicts or production performance.

Required tests cover the [persona matrix](persona_security_matrix.md), exact
decimals, immutable submission identity, replay, accepted replacement, rejected
revision, protected policy deployment and source-secret checks. Validate actual
code paths rather than claiming that source inspection proves runtime behavior.

## Reviewed Promotion

The [workflow](../workflows/promote.yml) runs credential-free PR verification.
Cloud plans and deployments are privileged manual operations on reviewed `main`,
behind a protected environment and independent reviewer. The client configures
those gates and the repository-specific OIDC trust. A merge alone does not grant
production permission or complete a two-host rollout.

Terraform owns infrastructure and grants; bundle/policy execution owns table DDL
and verified bindings. Functions are immutable and content-addressed; normal
deployment never detaches protection. One writer owns each principal/securable
grant pair. A stable service principal is independent of the provider's account,
but object ownership and human privileges still require explicit review.

## Secrets and State

Current source scanning rejects credential literals; it is not certification of
all source history. Runtime credentials use client-controlled secret references.
Terraform state and plans can contain secret values and require restricted access,
encryption, retention and audit. Easy Auth session storage and gateway bearer
tokens are sensitive. No secret is to be collected through a chat or checked into
the deliverable.

OIDC avoids a stored CI client secret, not every runtime secret. Rotation resources
act on a subsequent apply; operators must refresh consumers and verify continuity.

## Handover and Exit

1. Freeze the approved source version, dependencies, licenses, evidence and limitations.
2. Transfer by approved clone/fork/import to a client-controlled repository.
3. Configure client-owned state, identities, vault, review gates and environment settings.
4. Validate a synthetic staging deployment with live persona and lifecycle checks.
5. Obtain production disclosure, residency, recovery, migration and cost approval.
   Replace demo generation and separate the educational ledger before production;
   the repository has no automatic production-readiness switch.
6. Complete operator-led knowledge transfer and acceptance.
7. Revoke provider groups, sessions/tokens, RBAC, vault/GitHub rights and delegated
   ownership; review copies/exports and accessible credentials. Retain stable
   client runtime identities and verify continued operation.

The Analyst View must reconcile expected latest submissions with receiver state,
not equate latest rejected arrival with current publication. The Researcher role
requires disclosure approval: public values and row presence can reconstruct
withheld measures. Follow the [open synthetic challenge](../../SECURITY.md#statistical-reconstruction-challenge)
and restrict/remove the role where necessary.

The core pattern is technology-agnostic. Terraform supports alternative-provider
implementations, not automatic Azure/Databricks control portability. Evaluation
timing and cost are recorded with limits in [Release Evidence](../../docs/RELEASE_EVIDENCE.md#reference-evaluation-metrics).