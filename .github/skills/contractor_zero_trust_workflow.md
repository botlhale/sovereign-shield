# Contractor Zero-Trust Delivery Workflow

> **The problem.** An organisation needs specialist platform work on a system
> holding Protected B / nationally confidential data. The specialists it needs
> are exactly the people who should not hold that data. Institutions manage this
> today with NDAs, supervised environments and access reviews — controls that
> work, but that scale with headcount and decay with time.
>
> **The pattern.** Make the access unnecessary rather than merely governed. The
> contractor never holds production data at any point, and removing them
> afterwards is a small set of administrative actions rather than an audit
> exercise.

This is a **structural property of the architecture**, not a process wrapper
around it. The sections below state what makes it hold, and where it stops.

---

## 1. The three boundaries

| Boundary | Who crosses it | What crosses it |
| --- | --- | --- |
| **Specification** | Org → contractor | Structure, codelists, rulebook, persona matrix. No values. |
| **Execution** | Contractor, alone | Code, synthetic fixtures, local tests. No credentials. |
| **Promotion** | CI/CD identity, alone | Version-controlled artefacts. No human hands. |

No single actor spans all three. The contractor authors what runs in production
but never runs it there; the promotion identity runs it but is not authored by a
human at deploy time.

---

## 2. Phase 1 — Organisation preparation

The org produces two artefacts before the contractor starts. Both are
specifications, and neither contains a production record.

**The Minimal Viable Synthetic Dataset.** Structure, codelists, cardinality
magnitudes and required test coverage — see
[`mvsd_specification.md`](mvsd_specification.md). The contract is that the
corpus is *generated*, never sampled or perturbed. Perturbation preserves
distribution shape and is attackable; generation from a seed is not.

**The persona security matrix.** Group names, entitlements and the fail-closed
default — see [`persona_security_matrix.md`](persona_security_matrix.md). The
org owns this document because entitlement is a legal question, not an
engineering one. The contractor implements it; they do not define it.

The org also creates the Entra ID groups. It does **not** add the contractor to
any of them.

---

## 3. Phase 2 — Contractor execution boundary

Everything the contractor needs runs on a laptop with no cloud credentials.

| Capability | Local substitute | Why it is faithful |
| --- | --- | --- |
| Submissions | `generate_sovereign_submissions.py` | Emits real SDMX-ML 3.0 against the live public BIS DSD |
| Rulebook | `sdmx_rule_validator.py` + `checks_lbs.xls` | The genuine published BIS check set, parsed at runtime |
| SCD2 semantics | `local_pandas_scd2.py` | Mirrors the Spark state machine on pandas + delta-rs, no JVM |
| Persona matrix | `LocalDeltaBackend` in `uc_query.py` | Reimplements the row filter and mask in pandas |
| Serialization | `sdmx_ml_exporter.py` | ElementTree fallback works with no registry access |

### The honest caveat about the local mirror

`LocalDeltaBackend` is the one place the persona matrix is expressed **twice** —
once as SQL in the metastore, once as pandas for local execution. That is a
duplication, and duplication drifts.

It is accepted deliberately, with a specific mitigation: the offline persona
tests in `tests/test_persona_access_matrix.py` assert the *same* expectations
that the `--live` variant asserts against real Unity Catalog. When the mirror
drifts from the metastore, the live run fails. The mirror is a development
convenience whose correctness is verified against the real thing, not an
independent implementation anyone is asked to trust.

Unity Catalog remains the enforcement point in every deployed configuration.
`LocalDeltaBackend` is unreachable whenever `DATABRICKS_SERVER_HOSTNAME` is set.

### What the contractor is allowed to know

The design, in full. The security depends on group membership and metastore
policy — not on the architecture being secret. A contractor who understands the
row filter perfectly still resolves to zero rows once removed from the groups.

---

## 4. Phase 3 — Air-gapped promotion

The contractor opens a pull request. They cannot deploy it.

```
PR ──▶ offline test suite ──▶ human review ──▶ merge
                                                │
                                                ▼
                                    OIDC federated credential
                                                │
                                                ▼
                            terraform apply  ·  databricks bundle deploy
```

![The promotion plane and ownership boundary: pull request to offline tests (no credentials required) to review to merge to a short-lived OIDC token with no stored secret, which fans out to Terraform for infrastructure and to the Asset Bundle for data and policy, separated by a divider reading "one writer per object".](../../docs/sovereign-shield_technical_vision.jpg)

*The top two bands are this section. The contractor works entirely inside
"offline tests" — the only band that needs no credentials — and never crosses the
OIDC boundary.*

**Pipeline identity uses OIDC, not a stored secret.** GitHub Actions requests a
short-lived token from Entra ID via workload identity federation, scoped to a
specific repository, branch and environment. There is no client secret in
repository settings to leak, rotate or forget. See `.github/workflows/deploy.yml`.

**Terraform reads secrets, never receives them.** Configuration uses
`data "azurerm_key_vault_secret"` lookups rather than `var.client_secret`. The
contractor's code declares *which* secret it needs; the environment resolves the
value in memory at apply time. A `terraform.tfvars` containing a credential is
therefore not merely discouraged — there is no variable for it to populate.

**The data plane never sees a literal either.** Databricks reads credentials
through an Azure Key Vault-backed secret scope, so a notebook or job references
`dbutils.secrets.get(scope, key)` and the value is resolved by the platform.

### Ownership split at promotion

| Plane | Owner | Objects |
| --- | --- | --- |
| Infrastructure & access control | Terraform | Entra groups, service principals, OIDC federation, Key Vault, workspace, catalogs, schemas, storage credentials, external locations, SQL warehouse, `GRANT USE CATALOG` / `USE SCHEMA` / `SELECT` |
| Data & policy | DABs + `unity_catalog_triple_lock.sql` | Table DDL, policy UDFs, `SET ROW FILTER`, `SET MASK`, the quarantine view |

The split is deliberate and the boundary matters. Row filters and masks evolve
with the data model and are re-applied on every pipeline run through a
detach → replace → re-attach sequence. If Terraform also owned them it would
report drift after every run, and an `apply` could detach a live filter
mid-query. One writer per object.

---

## 5. The zero-secret guarantee

`tests/test_secret_decoupling.py` scans the repository for connection strings,
API keys, private-key blocks, client secrets and hardcoded bearer tokens. It runs
on every pull request.

The guarantee is structural rather than aspirational:

* Provisioning scripts pipe credentials straight from `az ad sp create-for-rbac`
  into `az keyvault secret set` — never echoed, never written to disk.
* `pre_auth.ps1` hydrates process-scoped environment variables at run time and
  **discovers** the vault by prefix rather than hardcoding its name.
* Container Apps resolves credentials through
  `keyvaultref:...,identityref:system` — the platform injects them, no value
  passes on a command line.
* Databricks Apps injects its own managed service principal's credentials into
  the runtime; nothing is stored in the repository.

The corollary is that a leaked repository is not a data incident. It contains no
credential and no observation.

---

## 6. Revocation

Three actions, none of which touch the delivered code:

1. **Rotate the service principal** — Terraform re-mints the dissemination proxy
   credential every 90 days on its own, and
   `terraform apply -replace="module.identity.azuread_service_principal_password.public_proxy"`
   forces it immediately; `sh/kv_spn_remediation.sh` does the same for the CI/CD
   principal. The secret is overwritten under the **same name**, so any copy the
   contractor retained is dead immediately and the pipeline continues working
   with **no code change** — consumers resolve secrets by name, never by value.
2. **Remove the Key Vault access policy** for the contractor's identity. Without
   it they cannot hydrate a session at all.
3. **Remove them from every Entra ID group.** The row filter grants rows only on
   positive membership and fails closed on no match, so a former contractor who
   somehow retained a valid login resolves to zero groups and therefore zero rows.

> The mechanism that stops Canada seeing UK data is the mechanism that stops a
> former contractor seeing any data. There is no separate off-boarding feature
> that could rot or be tested less rigorously than the primary one.

---

## 7. Where the pattern stops

Stated plainly, because this is what a reviewer should press on.

* **Someone must hold admin rights** to run the rotation and manage groups. The
  pattern shrinks the trusted set to the organisation's own administrators; it
  does not eliminate it.
* **The contractor knows the design.** Intentional, but it does mean the pattern
  protects data, not architectural novelty.
* **Calibration against real distributions cannot be contracted out.** The only
  tuned constant here is the disclosure-dominance threshold (`0.60`), and that is
  a policy decision rather than a value learned from data. If a future
  requirement genuinely needs fitting to real distributions, that work sits
  *after* handover and inside the organisation's boundary.
* **Synthetic data cannot prove production performance.** Volumetrics,
  skew and cost behaviour at real scale need a production dry-run the contractor
  will not observe.
* **The local persona mirror can drift** between `--live` runs. It is verified,
  not proven.

---

## 8. Contractor checklist

Before opening a pull request:

- [ ] `pytest tests/` passes offline, with no cloud credentials present
- [ ] `pytest tests/test_secret_decoupling.py` passes
- [ ] No new dimension, group name or status literal invented — all trace to
      [`mvsd_specification.md`](mvsd_specification.md) or
      [`persona_security_matrix.md`](persona_security_matrix.md)
- [ ] Any new persona logic added to Unity Catalog SQL is mirrored in
      `LocalDeltaBackend` **and** asserted in `test_persona_access_matrix.py`
- [ ] `terraform plan` produces no diff against policy objects — those belong to
      the SQL DDL
- [ ] `databricks bundle validate -t dev` succeeds

---

## Related skills

* [`mvsd_specification.md`](mvsd_specification.md) — the synthetic corpus contract
* [`persona_security_matrix.md`](persona_security_matrix.md) — the entitlement the contractor implements
* [`triple_lock_security.md`](triple_lock_security.md) — the enforcement objects
* [`docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md`](../../docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md) — the same pattern for an engagement lead
