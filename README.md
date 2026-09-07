# Project SovereignShield: Zero-Trust Governance for SDMx 3.0 Submissions to International Bodies

> **What this is:** a working reference implementation exploring how **Azure Databricks and Unity Catalog** can express the security obligations of **international statistical data exchange** as platform-level constraints — the submission of confidential national banking statistics to an international body (BIS Locational Banking Statistics) under the **SDMx 3.0** standard. It complements, rather than replaces, the mature SDMx tooling institutions already operate.

> ### ⚠️ Disclaimer
>
> This is an **independent reference architecture**, inspired by the design of public statistical portals such as the BIS Data Explorer. It is **not** a system of, affiliated with, or endorsed by the Bank for International Settlements or any central bank.
>
> It operates on **100% synthetic mock data**. No real submission, observation or institution identifier exists anywhere in this repository. The BIS Locational Banking Statistics data structure and the consistency rulebook it uses are **published public standards artefacts**; the numbers flowing through them are generated.
>
> BIS and SDMx are referenced as typeset text throughout, never as reproduced logos.

![Sovereignty as a Platform Guarantee — three abstract reporting jurisdictions submit standardised documents along a pathway; an automated rule check deflects one submission into a "held for correction" tray while the rest continue into a governed data vault wrapped in three policy rings labelled "who you are", "what you may see" and "what is published"; four audiences (public, researcher, national analyst, auditor) draw from that single source through beams of increasing width.](docs/sovereign-shield_executive.jpg)

## 📖 Executive Summary

Every quarter, national central banks transmit confidential banking statistics to international organisations — the Bank for International Settlements, the IMF, the UN Statistics Division — encoded in **SDMx**, the standard for Statistical Data and Metadata (ISO 17369). That exchange carries three simultaneous obligations: national data sovereignty, cell-level confidentiality, and arithmetic consistency with a rulebook the submitting agency does not own.

Institutions already uphold these obligations rigorously today, using specialised open-source SDMx software (such as the SDMX Reference Infrastructure), dedicated application layers, and strict operational protocols developed over many years. That work is mature, and this project does not try to replace it.

SovereignShield asks an adjacent architectural question: *what happens if the same obligations are moved out of the application layer entirely and expressed as constraints of the cloud data platform itself?*

**Zero Trust is a network and application security model. This project re-imagines it for statistical submissions.** In this domain the perimeter is not a VPC — it is a national border, and a legal one. "Never trust, always verify" therefore resolves to a concrete mechanism: every consumer is re-authorised against Entra ID at query time, and entitlement is evaluated from the SDMx key itself.

Three properties follow, and each is expressed in Unity Catalog rather than in pipeline code:

| Obligation | Enforcement | Bypassable by application code? |
| --- | --- | --- |
| **Sovereignty** — a jurisdiction sees only its own rows | Row filter on `L_REP_CTY`, segment 9 of the SDMx key | No — attached to the table object |
| **Confidentiality** — protected observations never leave | Column mask keyed on `OBS_CONF` **and** the reporting jurisdiction | No — attached to the column |
| **Integrity** — nothing internally inconsistent is published | Atomic per-country-quarter validation against the BIS rulebook | No — the curated view is the only researcher path |

Because policy lives in the metastore, it is enforced identically through PySpark, a SQL warehouse, a BI tool, an ad-hoc JDBC session — or the public web portal and REST API described below. There is no code path that can forget to apply it, because it is not in the code path at all.

The validation rulebook is treated as **metadata, not code** — an approach the SDMx community has long advocated: BIS consistency checks are parsed from the published workbook at runtime, so a rulebook revision requires no deployment. Routine operator intervention in production is correspondingly reduced — credentials are hydrated from Azure Key Vault into session scope and never persisted, and all DDL is applied by an automated, version-controlled pipeline.

> **Status:** a complete, deployed, end-to-end reference architecture on Azure, running the genuine BIS LBS rulebook and real SDMx 3.0 message structures against realistic **synthetic** submissions. It is not connected to live reporting data, and it is an independent piece of work — not a production system of, nor endorsed by, any central bank or international organisation. It is published for scrutiny, and critique from SDMx practitioners is genuinely welcome.

---

## 🗺️ System Architecture

![Policy as a Metastore Object — four horizontal bands. A promotion plane runs pull request to offline tests to review to merge to a short-lived OIDC token. An ownership boundary splits Terraform (infrastructure and access) from the pipeline (data and policy) either side of a divider reading "one writer per object". A data plane routes validated submissions to a history table and failures to an audit-only quarantine, with the prior published record staying live. A consumption band shows the dissemination gateway choosing an identity but never choosing rows. All four connect into a policy enforcement point in Unity Catalog resolving five personas, ending with "no group — zero rows, fails closed".](docs/sovereign-shield_technical_vision.jpg)

Credentials never leave Azure Key Vault as literals, compute is ephemeral and single-node, and every consumer is resolved to an Entra ID security group at query time by Unity Catalog.

```mermaid
flowchart TB
    subgraph LOCAL["💻 Developer Workstation / CI Runner"]
        AUTH["pre_auth.ps1<br/>(dot-sourced into session)"]
        CLI["Databricks CLI<br/>bundle deploy / bundle run"]
    end

    subgraph AZURE["☁️ Azure Control Plane"]
        KV["🔐 Azure Key Vault<br/>kv-sovereignshield-28083"]
        SPN["🤖 Service Principal<br/>spn-sovereignshield-cicd"]
        ENTRA["👥 Microsoft Entra ID<br/>Security Groups"]
    end

    subgraph DBX["🧱 Azure Databricks Workspace"]
        DAB["Asset Bundle<br/>sovereignshield_sdmx_pipeline"]
        COMPUTE["Single-Node Job Cluster<br/>DBR 18.x - DS3_v2 - Spot<br/>USER_ISOLATION"]
        T1["1 - apply_security.py"]
        T2["2 - generate_sovereign_submissions.py"]
        T3["3 - scd2_merge_engine.py"]
    end

    subgraph UC["🛡️ Unity Catalog - dbw_sovereignshield.sovereign_shield"]
        MICRO["lbs_micro_transactions<br/>RLS: fn_rls_micro_country_lock"]
        MACRO["agg_sdmx_history<br/>RLS: fn_rls_multi_persona_lock<br/>DDM: fn_ddm_obs_conf_mask"]
        VIEW["v_agg_sdmx_published<br/>PUBLISHED + IS_CURRENT"]
    end

    subgraph PORTAL["🌐 Databricks App - sovereignshield-portal"]
        API["api_gateway.py<br/>FastAPI /api/v1"]
        UI["portal_ui.py<br/>BIS-style filter dashboard"]
        EXP["sdmx_ml_exporter.py<br/>SDMX-ML 3.0 / JSON / CSV"]
    end

    subgraph CONSUMERS["🎯 Governed Consumers"]
        ADMIN["sg-sovereignshield-admin"]
        SUB["sg-sovereignshield-submitter-*"]
        RES["sg-sovereignshield-researchers"]
        PUB["sg-sovereignshield-public"]
    end

    AUTH -->|az keyvault secret show| KV
    KV -->|ARM_CLIENT_ID / SECRET / TENANT_ID<br/>DATABRICKS_HOST| CLI
    KV -.->|stores credentials for| SPN
    CLI -->|OAuth M2M| DAB
    SPN -->|executes as implicit owner| DAB
    DAB --> COMPUTE
    DAB --> PORTAL
    COMPUTE --> T1 --> T2 --> T3
    T1 -->|DDL + policy binding| UC
    T3 -->|append ledger| MICRO
    T3 -->|SCD2 MERGE| MACRO
    MACRO --> VIEW
    ENTRA -.->|is_account_group_member| MACRO
    ENTRA -.->|is_account_group_member| MICRO
    UI --> API
    API --> EXP
    API -->|OBO token or public SPN| MACRO
    MACRO --> ADMIN
    MACRO --> SUB
    MACRO --> RES
    MACRO --> PUB
    MICRO --> SUB
    VIEW --> RES
```

**Trust boundary summary**

| Boundary | Enforced by | Guarantee |
| --- | --- | --- |
| Secret → Session | Azure Key Vault + OIDC federation (Terraform), dot-sourced `pre_auth.ps1` (quickstart) | No credential literal exists in git or on disk |
| Session → Workspace | OIDC workload identity federation via Asset Bundles | No human identity holds production DDL rights |
| Workspace → Data | Unity Catalog RLS / DDM | Policy travels with the table, not the query engine |
| Data → Consumer | Entra ID group resolution | Sovereignty evaluated per-row, per-caller, at runtime |
| Internet → Data | Portal runs as the caller, or as a public-tier SPN | The gateway selects an identity; it never selects rows |

---

## 🏗️ Modernized Architecture Stack

* **Compute Engine:** Azure Databricks (Runtime 18.x LTS)
* **Storage:** Delta Lake (SCD2 Historization)
* **Central Governance:** Unity Catalog (`USER_ISOLATION` Shared Compute)
* **Infrastructure as Code:** Terraform (identity, workspace, catalog, warehouse, gateway) + Databricks Asset Bundles (tables, policy functions, jobs)
* **Promotion:** GitHub Actions with OIDC workload identity federation — no client secret in repository settings
* **Processing Framework:** PySpark & Spark SQL
* **Dissemination:** Databricks Apps — FastAPI gateway and Tailwind portal in a single process; Azure Container Apps for the anonymous deployment
* **Standards Layer:** `pysdmx` for SDMx 3.0 XML and DSD resolution; BIS consistency checks parsed at runtime from `docs/reference_standards/checks_lbs.xls`

> **Design note — Terraform or Bicep.** Terraform is the primary declarative engine here because it spans Entra ID, Azure and Databricks in a single dependency graph. For the **Azure control plane alone**, Azure Bicep is interchangeable: resource groups, Key Vault, the Databricks workspace, the access connector and Container Apps all have direct Bicep equivalents, and an organisation standardised on Bicep loses nothing by using it for those. What Bicep cannot express is the Databricks provider layer — catalog, schema, grants and the SQL warehouse — which would remain Terraform or move to the Databricks CLI. The ownership boundary between infrastructure and the data/policy plane is unaffected by that choice.

## ⚡ Five-minute local evaluation

No Azure subscription, no Databricks workspace, no credentials. The security model
is verifiable offline, which is the whole point of the delivery pattern.

```powershell
git clone https://github.com/<owner>/sovereign-shield.git
cd sovereign-shield

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# The persona matrix, SDMx validation, contractor isolation and secret assertions
.venv\Scripts\python.exe -m pytest tests/ --no-header
```

Expect **59 passed, 12 skipped**. The skips are the `--live` tests that need a real
workspace and the `--stress` benchmarks that take minutes.

```powershell
# Generate a 100k-row multi-jurisdiction, multi-cadence corpus
.venv\Scripts\python.exe src/generate_stress_test_data.py --rows 100000 --frequencies "A,S,Q,M"

# Run the scale benchmarks against it
.venv\Scripts\python.exe -m pytest tests/test_scale_and_stress.py --stress
```

**The exercise worth doing.** Open [src/uc_query.py](src/uc_query.py), find
`_apply_persona`, and delete the segment-9 re-check from the masking logic. Re-run
the suite. Exactly one test should fail. If none does, you have reproduced the
defect this repository exists to prevent — see
[docs/technical_guide.md § Pass 8](docs/technical_guide.md).

---

## 📂 Project Structure

```text
.
├── databricks.yml                          # Asset Bundle configuration and deployment rules
├── steps.md                                # Operational rebuild runbook
├── .github/
│   ├── workflows/promote.yml               # OIDC promotion: verify -> plan -> apply -> bundle
│   └── skills/                             # Single source of truth for agents and reviewers
├── docs/                                   # Guides, reference, whitepaper, diagrams
│   └── reference_standards/checks_lbs.xls  # BIS LBS consistency checks (parsed at runtime)
├── terraform/                              # Infrastructure & access-control plane
│   └── modules/
│       ├── identity/                       # Entra groups, SPNs, OIDC federation, Key Vault
│       ├── databricks_workspace/           # Workspace, storage credential, secret scope, cluster policy
│       ├── unity_catalog_governance/       # Catalog, schema, additive grants, SQL warehouse
│       └── dissemination_gateway/          # Container Apps host for the anonymous tier
├── tests/                                  # Offline persona, SDMx, isolation, secret and scale assertions
├── sh/                                     # Idempotent quickstart provisioning (alternative to Terraform)
└── src/
    ├── unity_catalog_triple_lock.sql       # Data & policy plane: DDL, RLS, DDM, quarantine view
    ├── unity_catalog_grants.sql            # Access-control plane (Terraform owns this in IaC mode)
    ├── apply_security.py                   # Idempotent Spark SQL executor for the DDL
    ├── generate_sovereign_submissions.py   # Sovereign-isolated SDMx 3.0 XML submission generator
    ├── generate_stress_test_data.py        # High-volume, multi-cadence corpus for scale testing
    ├── sdmx_rule_validator.py              # Dynamic BIS rule engine + atomic batch quarantine
    ├── scd2_merge_engine.py                # Micro-to-macro aggregation and Delta SCD2 state machine
    ├── local_pandas_scd2.py                # Local pandas/delta-rs SCD2 fixture (no Spark required)
    ├── sdmx_ml_exporter.py                 # SDMX-ML 3.0 / SDMX-JSON 2.0.0 / SDMX-CSV 2.0.0 writer
    ├── uc_query.py                         # Persona-agnostic query layer over the governed history
    ├── api_gateway.py                      # Public Dissemination Gateway; dual-mode identity resolution
    ├── portal_ui.py                        # BIS-style portal router
    └── templates/portal.html               # Tailwind filter dashboard and export centre
```

Full file-by-file commentary: [docs/technical_guide.md](docs/technical_guide.md).

## 🔐 Infrastructure-as-Code & Decoupled Secret Injection

SovereignShield holds a hard constraint: **no credential literal ever enters the repository, the shell history, or a configuration file.** Terraform declares *which* secret is needed; the environment resolves the value in memory at apply time.

### Terraform is the primary path

```powershell
cd terraform
cp backend.hcl.example backend.hcl              # your state storage account
cp terraform.tfvars.example terraform.tfvars    # subscription_id, tenant_id
terraform init -backend-config=backend.hcl
terraform apply
```

One apply provisions the Entra persona groups, both service principals, the GitHub OIDC federated credentials, Key Vault, the Databricks workspace, the access connector and storage credential, the catalog and schema, the serverless SQL warehouse, and the Container Apps dissemination gateway.

**There is no variable that can carry a credential**, and that is enforced rather than asserted: `tests/test_secret_decoupling.py` fails the build if a secret-shaped Terraform variable is ever declared, or if any module output exposes a `.value`. Only *pointers* are permitted — `public_client_secret_id` holds a Key Vault resource id, never a secret.

Credentials reach their consumers three ways, none of which is a literal:

| Consumer | Mechanism |
| --- | --- |
| GitHub Actions | OIDC workload identity federation — no client secret in repository settings |
| Container Apps | `keyvaultref:...,identityref:...` resolved by the platform at start-up |
| Databricks jobs | Key Vault-backed secret scope, which stores a pointer rather than a copy |

Rotation is automatic: `time_rotating` re-mints the dissemination proxy credential every 90 days and writes it straight to Key Vault. Because consumers resolve secrets by **name**, rotation requires no code change and no redeploy.

| Key Vault Secret | Purpose |
| --- | --- |
| `spn-client-id` | SPN application ID → `ARM_CLIENT_ID` |
| `spn-client-secret` | SPN secret → `ARM_CLIENT_SECRET` |
| `spn-tenant-id` | Entra tenant → `ARM_TENANT_ID` |
| `databricks-workspace-url` | Target workspace → `DATABRICKS_HOST` |
| `public-spn-client-id` / `public-spn-client-secret` | Anonymous dissemination proxy |

### The `sh/` scripts are a quickstart, not the deployment path

`sh/` exists so the platform can be stood up on a laptop without a Terraform state backend — useful for a demo, a first look, or teaching the moving parts. Every script is idempotent and prints `[skip]` / `[create]`.

They are **not** the supported route to a governed environment. Terraform holds state, plans changes before making them, and is what CI runs. Where the two overlap they converge on the same result; where they differ, Terraform is authoritative.

Two capabilities remain script-only because no provider expresses them:

* `sh/databricks_account_setup.ps1` — Databricks **account**-level groups and workspace assignment. `is_account_group_member()` resolves account scope, and the Terraform Databricks provider addresses the workspace.
* `sh/kv_spn_remediation.sh` — deliberate, destructive credential rotation on demand.

### Session authentication for the quickstart path

```powershell
. .\sh\pre_auth.ps1
```

The leading `.` executes the script **in the current session scope**. Invoking it conventionally (`.\sh\pre_auth.ps1`) sets the variables inside a child scope destroyed the moment the script returns, leaving the CLI unauthenticated — a failure mode that presents confusingly as "the script ran fine but deploy still 401s."

The script discovers the vault by prefix rather than hardcoding a name (the suffix is randomised at creation), fails loudly on a missing secret rather than exporting an empty credential, and `.Trim()`s every value — `az ... -o tsv` appends a newline, and an unstripped secret produces an opaque authentication rejection rather than a parse error.

## 🚀 Deployment & Execution

Full sequence, including prerequisites and verification: **[steps.md](steps.md)**.

**1. Infrastructure and access-control plane:**

```powershell
cd terraform; terraform apply; cd ..
```

**2. Databricks account groups** (no Terraform equivalent):

```powershell
./sh/databricks_account_setup.ps1 -AccountId "<account-id>"
```

**3. Data and policy plane** — table DDL, policy UDFs, row filter and mask bindings:

```bash
databricks bundle deploy -t dev --var="warehouse_id=$(terraform -chdir=terraform output -raw sql_warehouse_id)"
databricks bundle run sovereignshield_sdmx_pipeline -t dev
```

**4. Bind table grants** now that the tables exist:

```powershell
cd terraform; terraform apply -var="grant_tables=true"; cd ..
```

In CI this is [`.github/workflows/promote.yml`](.github/workflows/promote.yml): offline verification → plan on pull requests → apply and bundle deploy on merge to `main`.

## 🧹 Teardown

The demo is not free to leave running. Tear down in reverse dependency order.

**Stop paying, keep the platform** — enough between demos:

```powershell
databricks apps stop sovereignshield-portal
cd terraform; terraform apply -var="deploy_dissemination_gateway=false"; cd ..
```

The SQL warehouse auto-stops after 10 idle minutes on its own. The job cluster is spot-priced and terminates on completion.

**Full teardown:**

```powershell
# 1. Data and policy plane first. Terraform does not own these objects and
#    will not remove them; a leftover row filter blocks the catalog destroy.
databricks bundle destroy -t dev

# 2. Release the table grants so the securables are no longer referenced.
cd terraform; terraform apply -var="grant_tables=false"

# 3. Everything Terraform owns.
terraform destroy
cd ..

# 4. Purge the soft-deleted Key Vault. purge_protection_enabled is on, so the
#    vault survives destroy by design and the name stays reserved until purged.
az keyvault purge --name <vault-name> --location canadacentral
```

Step 1 is not optional. Unity Catalog refuses to drop a schema whose tables carry live row filters, and `terraform destroy` reports a confusing dependency error rather than naming the cause.

**What survives on purpose:**

| Resource | Why | Remove with |
| --- | --- | --- |
| Databricks **account** groups and service principals | Account scope, outside the workspace Terraform manages | Account console, or `sh/databricks_account_setup.ps1` in reverse |
| Entra ID persona **users** | Never created by Terraform; membership is an administrative act | `az ad user delete` |
| Terraform state storage account | Bootstrap resource, created before the configuration exists | `az group delete -n rg-sovereignshield-tfstate` |

**Verify nothing is billing:**

```powershell
az resource list --resource-group rg-sovereignshield --output table
```

An empty result means the teardown is complete. If the resource group itself lingers, `az group delete -n rg-sovereignshield` — but prefer `terraform destroy` first so state stays consistent with reality.

## 🛡️ How the guarantees are enforced

Four pillars carry the architecture. Each is a link into the detail rather than a
summary of it — the full implementation narrative is in
**[docs/technical_reference.md](docs/technical_reference.md)**.

### 1. Zero-Access Contractor Pattern

The specialist you need for confidential data work is, by definition, someone who
should not have the data. So the build happens against a **Minimal Viable Synthetic
Dataset** specified by the client, promotion runs through OIDC federation with no
stored secret, and revocation is three actions that touch no code.

→ [Onboarding playbook](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md) ·
[Contractor workflow](.github/skills/contractor_zero_trust_workflow.md)

### 2. Triple-Lock Security

Entitlement is a property of the table, not of the application. A row filter, a
column mask and a curated view are attached to catalog objects and evaluated per
caller, per row, at query time.

| | Lock 1 — RLS | Lock 2 — DDM | Lock 3 — Quarantine view |
| --- | --- | --- | --- |
| **Object** | `fn_rls_multi_persona_lock` | `fn_ddm_obs_conf_mask` | `v_agg_sdmx_published` |
| **Granularity** | Row | Cell | Result set |
| **Threat** | Cross-border leakage | Confidential value disclosure | Unvalidated data published |

Five personas resolve against Entra ID. The fifth matters most: **a principal in no
group sees zero rows.** Public is an explicit group, not a fall-through default,
which is why off-boarding a contractor and enforcing sovereignty between two
nations are the same mechanism.

→ [Triple-Lock detail](docs/technical_reference.md) ·
[Persona matrix](.github/skills/persona_security_matrix.md)

### 3. Public Dissemination Gateway

One service decides *which identity* a query runs as. Unity Catalog decides *what
that identity may see*. There is no persona branch anywhere in the serving code, so
a fully compromised gateway still cannot return a confidential observation.

→ [Gateway and SDMx serialization](docs/technical_reference.md)

### 4. SDMx 3.0 Conformance

Real SDMX-ML 3.0, SDMX-JSON 2.0.0 and SDMX-CSV 2.0.0 messages, serialised with
`pysdmx` against the published BIS LBS structure. The consistency rulebook is parsed
from the published workbook at runtime, so a standards revision needs no deployment.

→ [Validation engine](.github/skills/sdmx_lbs_validation.md)

---

## 📚 Documentation

Routed by what you are trying to establish.

| If you are… | Start here | Then |
| --- | --- | --- |
| **Reading the code** | [Technical guide](docs/technical_guide.md) — an eight-pass reading order | [Technical reference](docs/technical_reference.md) |
| **Assessing the security model** (CISO / risk) | [Persona security matrix](.github/skills/persona_security_matrix.md) | [Triple-Lock detail](docs/technical_reference.md) · [Test suite](tests/test_persona_access_matrix.py) |
| **Evaluating the business case** (SLT) | [Executive vision](docs/executive_vision.md) — case, governance posture, positioning | [Whitepaper](docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md) |
| **Deploying it** (platform / DevOps) | [steps.md](steps.md) — runbook, Stage 0 to teardown | [Terraform](terraform/main.tf) · [CI workflow](.github/workflows/promote.yml) |
| **Sizing it for production** | [Scaling blueprint](docs/technical_guide.md) | [Cluster policy](terraform/modules/databricks_workspace/compute.tf) |
| **Engaging a contractor** | [Onboarding playbook](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md) | [Contractor workflow](.github/skills/contractor_zero_trust_workflow.md) |
| **Consuming the API** | [Technical vision](docs/technical_vision.md) — data model, cadences, endpoints | [Gateway detail](docs/technical_reference.md) |
| **Checking SDMx conformance** (statistical audit) | [SDMx LBS validation](.github/skills/sdmx_lbs_validation.md) | [MVSD specification](.github/skills/mvsd_specification.md) |
| **Looking at diagrams** | [Architecture diagrams](docs/ARCHITECTURE_DIAGRAMS.md) | [Image prompts](docs/image_prompts.md) |
| **Presenting it** | [Executive vision](docs/executive_vision.md) | [Public write-up](docs/LINKEDIN_POST.md) |

---


## 📝 Bundle Configuration

[`databricks.yml`](databricks.yml) is the orchestration matrix. **Task order is a
security property, not a convenience:** the Triple-Lock DDL runs first, so no table
ever exists unprotected.

```text
setup_triple_lock_schema  →  generate_synthetic_data  →  run_scd2_merge
(apply_security.py)          (generate_sovereign_       (scd2_merge_engine.py)
                              submissions.py)
```

The job cluster is pinned to `data_security_mode: USER_ISOLATION` and defaults to
`num_workers: 0`. Both are bounded by the Terraform cluster policy in
[compute.tf](terraform/modules/databricks_workspace/compute.tf), which fixes the
security mode and defines the sizing envelope — see
[the scaling blueprint](docs/technical_guide.md) for how to widen it.

---

## 🔑 Operational Prerequisites

1. **SPN group membership** — add `spn-sovereignshield-cicd` to `sg-sovereignshield-admin`. Object ownership does not exempt a principal from a row filter; without this the merge engine reads an empty target and silently duplicates history.
2. **Key Vault access** — the deploying identity needs `get` on secrets in `kv-sovereignshield-28083`. The vault was created with `--enable-rbac-authorization false`, so access is granted via **access policies**, not Azure RBAC role assignments.
3. **Session authentication** — always **dot-source** the loader (`. .\sh\pre_auth.ps1`). Running it as a child process sets the variables in a scope that is discarded on return.
4. **Credential hygiene** — no credential exists in the repository, and `tests/test_secret_decoupling.py` enforces that on every commit. Terraform rotates the dissemination proxy credential automatically every 90 days via `time_rotating`; `sh/kv_spn_remediation.sh` performs a deliberate, immediate rotation of the CI/CD principal when you need one.
5. **Entra ID groups** — `sg-sovereignshield-admin`, `sg-sovereignshield-submitter-<cc>`, `sg-sovereignshield-researchers`, and `sg-sovereignshield-public` must exist before the Triple-Lock DDL runs; the security functions resolve membership at query time via `is_account_group_member`. `terraform/modules/identity` provisions them, and `sh/databricks_account_setup.ps1` mirrors them into the Databricks **account** — account scope is what `is_account_group_member` reads, and workspace-scoped groups of the same name will never match.
6. **Public portal principal** — `terraform/modules/identity` provisions `spn-sovereignshield-public` and adds it to `sg-sovereignshield-public`. It is created with **no Azure RBAC role assignment at all**: its entire entitlement is the row filter. It must also be added to the Databricks account — otherwise the fail-closed default leaves the public portal showing nothing, which looks like an outage rather than a policy decision.
7. **SQL warehouse** — the portal reads through a warehouse passed as `--var="warehouse_id=..."` at deploy time. The warehouse grants no entitlement of its own; it is the engine the row filter is evaluated in.
8. **Two-pass apply** — leave `grant_tables = false` on the first apply. Tables are created by the Asset Bundle, and a grant against a securable that does not yet exist fails the apply.
9. **GitHub repository controls** — run `sh/github_environment_setup.ps1` before relying on the promotion workflow. GitHub creates an environment implicitly on first reference **with no protection rules**, so `environment: production` is decorative until required reviewers, self-review prevention and a protected-branch policy are configured. Protect `main` as well: restricting deployments to protected branches is vacuous if no branch is protected.
10. **Action pinning** — every action in `.github/workflows/promote.yml` is pinned to an immutable commit SHA with the release recorded in a trailing comment. A tag is a movable pointer and `@main` re-resolves on every run; either would let an upstream compromise reach a job holding a token that can apply infrastructure. Verify before bumping one: `gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq .object.sha`.

---

## 🤝 Safe Engagement & Clean Handover

Specialist platform work is frequently delivered by people who should not hold the
data they are governing. Institutions manage this well today with NDAs, supervised
environments and access reviews. SovereignShield explores how much of that burden
the platform itself can absorb: **the specialist never needs access to real data at
any point**, and **removing them afterwards is a small set of administrative actions
rather than an audit exercise**.

**Why the build never needs real data.** Submissions are generated, not sourced. The
rulebook is a published standards artefact. The security deliverable is declarative
DDL, reviewable without executing against a real row. Credentials are hydrated from
Key Vault into session scope, never stored. The only tuned constant in the system is
the disclosure-dominance threshold (`0.60`) — a policy decision, not a value learned
from data.

**The cut-off is three actions, none of which touch the delivered code:** rotate the
service principal, remove the Key Vault access policy, remove the builder from every
Entra ID group. The third is the interesting one — `fn_rls_multi_persona_lock` grants
rows only on positive membership, so a former builder resolves to zero groups and
therefore zero rows.

> Off-boarding a person and enforcing sovereignty between two nations are **the same
> code path**. There is no separate revocation feature that could rot, be forgotten,
> or be tested less rigorously than the primary one.

**Where this model stops** — the part reviewers should press on — is documented
honestly in the playbook, along with the full three-phase framework and acceptance
checklist.

→ **[Enterprise onboarding playbook](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md)** ·
[Contractor workflow](.github/skills/contractor_zero_trust_workflow.md)

---

## 🎤 Presentation & Communication Assets

| Asset | Contents |
| --- | --- |
| [docs/executive_vision.md](docs/executive_vision.md) | Strategic business case, governance posture, regulatory positioning, and a five-minute presenting narrative |
| [docs/technical_vision.md](docs/technical_vision.md) | Data model, multi-frequency cadences, Dissemination Gateway API, and the architecture-review Q&A |
| [docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md](docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md) | Full executive whitepaper, PDF-ready |
| [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) | Live-renderable Mermaid diagrams (system topology, ownership boundary, atomic quarantine sequence, triple-lock enforcement path) |
| [docs/image_prompts.md](docs/image_prompts.md) | The prompts that generate the two rendered diagrams |
| [docs/LINKEDIN_POST.md](docs/LINKEDIN_POST.md) | Public write-up, primary and long-form versions |
