# Triple-Lock Policy and Deployment Contract

Use this reference for policy SQL, protected DDL, runtime selection and ownership.
The owners are [unity_catalog_triple_lock.sql](../../src/unity_catalog_triple_lock.sql)
and [apply_security.py](../../src/apply_security.py).

## Security Boundary

Unity Catalog evaluates Databricks account-group membership on supported query
paths. The reference uses `USER_ISOLATION`; dedicated/other access modes have
runtime-specific support requirements and are not universally bypasses. Logical
country segregation is not physical residency. Privileged storage/control-plane
access, gateway tokens, archives and downloaded products remain trusted boundaries.

Setup reconciles Entra identities with account groups. It does not provide
continuous Entra deprovisioning. The gateway chooses identity and lifecycle/user
filters, and UC independently enforces table row/value entitlements. A compromised
gateway can misuse the tokens and results it handles.

## Three Controls

| Control | Decision | Contract |
| --- | --- | --- |
| Macro RLS | `TIME_SERIES_CODE`, `BATCH_STATUS`, `OBS_CONF` plus account memberships | Admin all; own-country submitter all states; researcher published; public/foreign submitter published explicit `F` |
| DDM | `DECIMAL(38,3)` measure, classification and reporting country | Admin or own country reveal; otherwise explicit `F` only; unknown/missing classification masks to `NULL` |
| Published product | `BATCH_STATUS='PUBLISHED' AND IS_CURRENT=true` | Current accepted publication; authorized audit products remain distinct |

The row filter does not itself enforce current-state selection. Dynamic UC views
can evaluate caller membership; the base table is used here to support both current
and audit workflows, not because membership functions always run as the view owner.

The **Analyst View** is submitter reconciliation of expected latest filings with
actual IDs, timestamps, values and validation outcomes. The latest rejected
filing must not be presented as the current accepted publication.

## Educational Ledger and Archive

The modeled international intake accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely to explain the calculation of realistic statistical
observations. The demo ledger is not an institutional intake requirement or system
deliverable. Its separate country filter permits administrators and own-country
submitters; public and researcher roles have no grants. The source filing volume
is administrator-only because volumes cannot carry table RLS or masks.

## Protected DDL Lifecycle

1. Inspect existing table compatibility before policy mutation. Legacy incompatible
   decimal/history schemas require explicit migration.
2. Create immutable content-addressed policy functions and verify definitions.
3. Create initial tables with inline policies before loading or granting access.
4. Rebind existing protected objects without detaching protection; verify actual UC
   binding metadata and propagate errors.
5. Keep Terraform as the grants writer and the bundle as the policy-binding writer.
   The script-only grants path is an alternative owner, never a concurrent one.

A failed multi-object deployment may leave different protected function versions
on different objects; no cross-object atomic migration is claimed. Never use
`DROP ROW FILTER` or `DROP MASK` as routine idempotency steps. Do not copy obsolete
unprotected or floating-point DDL examples into a deployed schema.

The runtime principal must have the explicit admin persona to access complete
history during merges. Run-as permission and object ownership are separate;
neither CI nor a service principal automatically removes human privileges.

## Statistical Reconstruction

Published totals and the presence of researcher-visible observations can reveal
masked values without violating RLS or DDM. The synthetic dominance threshold
is not complete statistical disclosure control. The
[community challenge](../../SECURITY.md#statistical-reconstruction-challenge)
invites synthetic tests; the data authority must restrict or remove the Researcher
role if existence disclosure makes inference trivial and approve public release
controls independently.

## Verification and Portability

[Policy tests](../../tests/test_policy_deployment.py) exercise failure handling;
[live checks](../../src/live_runtime_checks.py) verify actual binding metadata.
Use the [migration gate](../../docs/RELEASE_EVIDENCE.md#mandatory-migration-gate)
and [full offboarding contract](../../docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md#6-offboarding-and-continuity).

The policy requirements are technology-agnostic; this SQL and identity integration
are platform-specific. Terraform-supported AWS, GCP, Fabric or open-source ports
require equivalent enforcement and lifecycle tests, not just matching resource names.