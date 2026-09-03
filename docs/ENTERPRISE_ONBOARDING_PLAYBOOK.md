# Enterprise Onboarding Playbook

> **For:** the engagement lead, the data governance owner, and the platform
> administrator who will hold the keys after the specialists leave.
>
> **Scope:** how to run a specialist platform engagement on a system holding
> nationally confidential data, without the specialists ever holding that data,
> and without off-boarding becoming an audit exercise.

---

## The dilemma this addresses

The work needs people who have built sovereign data platforms before. Those
people are, almost by definition, outside the organisation. The data they would
be working on is Protected B or nationally confidential.

The usual resolution is procedural: NDAs, supervised environments, time-boxed
access, quarterly access reviews. Institutions run this well. But the controls
scale with headcount, decay between reviews, and leave a residue — accounts,
group memberships and credentials whose removal has to be *verified* rather than
*guaranteed*.

SovereignShield explores a different resolution: **make the access unnecessary
rather than merely governed.** The specialist authors what runs in production and
never runs it there. Removing them is three administrative actions, none of which
touch the delivered code.

This is a structural property of the architecture. Section 5 states where it
stops.

---

## Phase 1 — Client organisation setup

Two artefacts, produced before the specialist starts. Both are specifications.
Neither contains a production record.

### 1.1 Define the Minimal Viable Synthetic Dataset

The MVSD is a **data contract**: structure, codelists, cardinality magnitudes and
required test coverage. Full specification in
[`.github/skills/mvsd_specification.md`](../.github/skills/mvsd_specification.md).

| Exported | Withheld |
| --- | --- |
| The DSD as published SDMX-ML | Observation values |
| Codelists as code/label pairs | Institution identifiers |
| The consistency rulebook | Real `(country, period)` pairs from an unpublished cycle |
| Cardinality *magnitudes* per dimension | Exact row counts of a confidential breakdown |
| The disclosure-control threshold, as policy | Anything invertible back to a cell |

One rule does the heavy lifting: **the corpus is generated, never sampled or
perturbed.** Perturbation preserves distribution shape and is attackable.
Generation from a seed is not.

The MVSD must exercise every control, or a test silently stops meaning anything:

- **Three reporting jurisdictions** (`CA`, `US`, `GB`) so isolation is
  distinguishable and a filter that returns everything is detectable.
- **Free and confidential rows in more than one jurisdiction.** A single-country
  corpus cannot detect a mask that checks group membership without checking the
  reporting country — which is a real defect class, not a hypothetical.
- **A revision of an already-published series**, so expiry is exercised. A
  simple `Q1 → Q2` progression only tests append.
- **Deliberately malformed records**, because a realistic corpus structurally
  cannot trigger a reconciliation check.

### 1.2 Define the persona security matrix

Group names, entitlements and the fail-closed default:
[`.github/skills/persona_security_matrix.md`](../.github/skills/persona_security_matrix.md).

The organisation owns this document. Entitlement is a legal question, not an
engineering one — the specialist implements it, they do not define it.

| Persona | Entra ID group | Sees |
| --- | --- | --- |
| Anonymous public | `sg-sovereignshield-public` | Published, free-to-publish only |
| Researcher | `sg-sovereignshield-researchers` | All published; confidential values `NULL` |
| Regional submitter | `sg-sovereignshield-submitter-<cc>` | Own jurisdiction in full; foreign published+free |
| Central auditor | `sg-sovereignshield-admin` | Everything, including SCD2 history |
| *No membership* | — | **Nothing** |

### 1.3 Create the identities

`terraform/modules/identity` provisions the persona groups, both service
principals and the OIDC federated credentials in one apply. `sh/` holds an
imperative quickstart for laptop demos; it is not the route to a governed
environment. The specialist is added to **none** of these groups.

Groups must exist at the Databricks **account** level. `is_account_group_member()`
does not resolve workspace-scoped groups, which look identical in the console and
silently match nothing — the single most common cause of "deployment worked, no
data visible". No Terraform provider addresses account scope, so
`sh/databricks_account_setup.ps1` mirrors them and remains a required step.

---

## Phase 2 — Contractor execution boundary

Everything the specialist needs runs on a laptop with no cloud credentials.

| Capability | Local substitute | Fidelity |
| --- | --- | --- |
| Submissions | `generate_sovereign_submissions.py` | Real SDMX-ML 3.0 against the live public BIS DSD |
| Rulebook | `sdmx_rule_validator.py` + `checks_lbs.xls` | The genuine published BIS check set, parsed at runtime |
| Historisation | `local_pandas_scd2.py` | Mirrors the Spark state machine on pandas + delta-rs, no JVM |
| Persona matrix | `LocalDeltaBackend` in `uc_query.py` | Reimplements the row filter and mask in pandas |
| Serialization | `sdmx_ml_exporter.py` | Local writer when the registry is unreachable |

```bash
pip install -r requirements.txt
pytest tests/            # 58 assertions, no credentials required
```

### The duplication, stated plainly

`LocalDeltaBackend` is the one place the persona matrix exists twice — as SQL in
the metastore, and as pandas for local execution. Duplication drifts.

It is accepted with a specific mitigation: the offline persona tests assert the
*same* expectations that the `--live` variant asserts against real Unity Catalog.
When the mirror drifts, the live run fails. It is a convenience whose correctness
is verified against the real thing, not an independent implementation anyone is
asked to trust. Unity Catalog remains the enforcement point in every deployed
configuration, and the mirror is unreachable once a workspace is configured.

---

## Phase 3 — Air-gapped promotion

```
PR ──▶ offline tests ──▶ human review ──▶ merge
                                            │
                                            ▼
                             OIDC federated credential
                                            │
                        ┌───────────────────┴───────────────────┐
                        ▼                                       ▼
            terraform apply                        databricks bundle deploy
    (infrastructure & access control)                 (data & policy plane)
```

### Ownership split

| Plane | Owner | Objects |
| --- | --- | --- |
| Infrastructure & access control | Terraform | Entra groups, service principals, OIDC federation, Key Vault, workspace, access connector, storage credential, external location, catalog, schema, SQL warehouse, `USE CATALOG` / `USE SCHEMA` / `SELECT` |
| Data & policy | DABs + `unity_catalog_triple_lock.sql` | Table DDL, policy UDFs, `SET ROW FILTER`, `SET MASK`, the quarantine view |

The boundary is not stylistic. Row filters are detached and re-attached on every
pipeline run so the functions they bind can be replaced. If Terraform also owned
them it would report drift after every run, and an apply could detach a live
filter mid-query. **One writer per object.**

Grants use the additive `databricks_grant` resource, never the authoritative
`databricks_grants`, which would revoke anything it does not declare.

### Why OIDC rather than a stored secret

GitHub Actions requests a short-lived token from Entra ID via workload identity
federation. There is no client secret in repository settings to leak, rotate or
forget.

The federated credential is scoped to one repository **and** one environment. A
subject of `ref:refs/heads/*` would let any branch assume the production
identity and defeat the review gate entirely.

### Deployment ordering

```bash
terraform apply                                   # 1. infrastructure + catalog
./sh/databricks_account_setup.ps1 -AccountId ...  # 2. account groups + assignment
databricks bundle deploy -t dev --var="warehouse_id=$(terraform output -raw sql_warehouse_id)"
databricks bundle run sovereignshield_sdmx_pipeline -t dev   # 3. tables + policies
terraform apply -var="grant_tables=true"          # 4. table grants, now bindable
```

Step 4 is separate because a grant on a securable that does not yet exist fails
the apply. Making the ordering explicit beats a run that dies halfway and leaves
the platform partially granted.

> **Design note — Terraform or Bicep.** Terraform is used here because it spans
> Entra ID, Azure and Databricks in one graph. For the Azure control plane alone,
> Bicep is interchangeable: resource groups, Key Vault, the workspace, the access
> connector and Container Apps all have direct Bicep equivalents. What Bicep
> cannot express is the Databricks provider layer — catalog, schema, grants,
> warehouse — which would remain Terraform or move to the Databricks CLI. The
> ownership boundary above is unaffected either way.

---

## Phase 4 — The zero-secret guarantee

`tests/test_secret_decoupling.py` runs on every pull request and scans for
connection strings, API keys, private-key blocks, client secrets and hardcoded
bearer tokens.

The guarantee is structural:

* **Provisioning** pipes credentials straight from `az ad sp create-for-rbac`
  into `az keyvault secret set` — never echoed, never written to disk.
* **Session auth** hydrates process-scoped environment variables at run time and
  discovers the vault by prefix rather than hardcoding a name.
* **Terraform** has no variable that could carry a credential. Secret-shaped
  variable names fail the build; only pointers (`*_secret_id`) are permitted.
* **Container Apps** resolves credentials through
  `keyvaultref:...,identityref:...` — the platform injects them, and no value
  passes on a command line or enters Terraform state.
* **Databricks** reads through a Key Vault-backed secret scope, which stores a
  pointer rather than a copy, so rotation takes effect immediately.

The corollary: **a leaked repository is not a data incident.** It contains no
credential and no observation.

> The scanner earned its place. It initially *missed* a real password hidden in a
> shell default expansion (`${VAR:-literal}`) because the `$` prefix looked like
> a safe reference. It now unwraps those, and the password it found has been
> replaced with per-run generation.

---

## Phase 5 — Revocation

Three actions, none of which touch the delivered code:

1. **Rotate the service principal.** Terraform re-mints the dissemination proxy
   credential automatically every 90 days (`time_rotating`); for an immediate
   rotation use `terraform apply -replace="module.identity.azuread_service_principal_password.public_proxy"`,
   or `sh/kv_spn_remediation.sh` for the CI/CD principal. Either way the secret is
   overwritten under the **same name**, so any retained copy dies immediately and
   the pipeline keeps working with no code change — every consumer resolves
   secrets by name, never by value.
2. **Remove the Key Vault role assignment.** Without it they cannot hydrate a
   session at all.
3. **Remove them from every Entra ID group.** The row filter grants rows only on
   positive membership and fails closed, so a former specialist who somehow
   retained a valid login resolves to zero groups and therefore zero rows.

> The mechanism that stops Canada seeing UK data is the mechanism that stops a
> former contractor seeing any data. There is no separate off-boarding feature
> that could rot, be forgotten, or be tested less rigorously than the primary one.

---

## Where this model stops

The parts a reviewer should press on:

* **Someone must hold admin rights** to run rotation and manage groups. This
  shrinks the trusted set to the organisation's own administrators; it does not
  eliminate it.
* **The specialist knows the design.** Intentional — security depends on group
  membership and metastore policy, not on architectural secrecy. But it does mean
  the pattern protects data, not novelty.
* **Calibration against real distributions cannot be contracted out.** The only
  tuned constant is the disclosure-dominance threshold (0.60), and that is a
  policy decision. Work that genuinely needs fitting to real distributions sits
  *after* handover, inside the organisation's boundary.
* **Synthetic data cannot prove production behaviour.** Volumetrics, skew and
  cost at real scale need a dry-run the specialist will not observe.
* **The local persona mirror can drift** between `--live` runs. It is verified,
  not proven.
* **Account-level group management remains partly manual.** Terraform provisions
  Entra groups; mirroring them into the Databricks account is a separate script,
  and a mismatch fails closed rather than loudly.

---

## Acceptance checklist

Before the engagement closes:

- [ ] `pytest tests/` passes with no cloud credentials present
- [ ] `pytest tests/ --live` passes against the real workspace for all four personas
- [ ] `terraform plan` shows no diff against policy objects — those belong to the SQL DDL
- [ ] The generator has been re-run inside the organisation's boundary and its
      schema diffed against production metadata
- [ ] Rotation has been exercised once, and the pipeline still deploys
- [ ] The specialist's group memberships and Key Vault role assignments are removed
- [ ] A query as the removed identity returns **zero rows**, not an error

---

## Related material

* [`.github/skills/mvsd_specification.md`](../.github/skills/mvsd_specification.md) — the data contract
* [`.github/skills/persona_security_matrix.md`](../.github/skills/persona_security_matrix.md) — the entitlement model
* [`.github/skills/contractor_zero_trust_workflow.md`](../.github/skills/contractor_zero_trust_workflow.md) — the same pattern for the engineer
* [`docs/ARCHITECTURE_DIAGRAMS.md`](ARCHITECTURE_DIAGRAMS.md) — renderable topology
* [`steps.md`](../steps.md) — the operational rebuild runbook
