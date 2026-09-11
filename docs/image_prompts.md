# Image Prompts

The two prompts that produce the rendered diagrams committed in this repository.
Both are self-contained and one-shot: paste whole into Gemini, Microsoft 365
Copilot, DALL·E or Midjourney. No compositing.

| Prompt | Renders | Audience |
| --- | --- | --- |
| [Executive](#executive-prompt) | `sovereign-shield_executive.jpg` | SLT, board, non-technical sponsors |
| [Technical](#technical-prompt) | `sovereign-shield_technical_vision.jpg` | Architects, security advisors, review boards |
| [Terraform deployment lifecycle](#terraform-deployment-lifecycle-prompt) | `sovereign-shield_deployment_lifecycle.jpg` | Enterprise architects, platform engineers, delivery leads |

## Attribution constraints

Both prompts forbid vendor logos, national flags and identifiable institutional
buildings, and both mandate an on-image caption stating synthetic data and
non-affiliation.

| Constraint | Reason |
| --- | --- |
| Vendors as typeset text only | Naming a product to describe what was used is nominative use. A reproduced brand mark implies partnership or endorsement |
| No flags, no bank facades | They read as *"this is a real central bank system"* |
| Caption inside the image | It survives being screenshotted out of the deck |
| Nothing logo-shaped requested | Image models render trademarks inaccurately, which is worse than omitting them |

Not legal advice. Route external material through whoever normally reviews it.

---

## Terraform deployment lifecycle prompt

```text
Create a comprehensive, polished 16:9 enterprise architecture infographic titled:

"SovereignShield — From Empty Subscription to Governed Statistical Portal"

SUBTITLE:
"Terraform deployment lifecycle · SDMx 3.0 ingestion · persona-aware dissemination · client handover"

AUDIENCE:
Seasoned Enterprise Data Architects, cloud platform architects, security
architects and technical delivery leads. The image must communicate the full
resource and technology sequence in under 60 seconds of scanning.

VISUAL STYLE:
- Premium enterprise architecture board, precise and restrained.
- White or very pale grey background, deep navy headings, teal for successful
  data flow, Azure blue for cloud resources, amber for deferred gates, muted red
  only for quarantine.
- Use a left-to-right numbered lifecycle with nine sequential stages connected
  by one strong horizontal path. Use swimlanes to show where work runs.
- Compact, information-dense, readable at 4K and when reduced to a LinkedIn
  carousel slide.
- Flat vector components, subtle shadows, square or 6px-radius containers.
- No decorative gradients, orbs, stock people, national flags or institutional
  buildings.
- Technology names may be written as text. Do not reproduce vendor logos or
  imply endorsement.

LAYOUT:

Top band — "OPERATOR & AUTOMATION"
Show a Windows workstation, PowerShell 5.1, Azure CLI, Databricks CLI,
Terraform, Python/pytest and Git. Show GitHub Actions with OIDC as an optional
promotion path, visually distinct from local interactive deployment.

Middle band — "AZURE & DATABRICKS CONTROL PLANE"
Show Azure Subscription, Resource Groups, Azure Storage remote Terraform state,
Microsoft Entra ID, Azure Key Vault, Azure Databricks workspace, access
connector, Unity Catalog, serverless SQL warehouse, Azure Container Registry,
Azure Container Apps and its separate Easy Auth token-store Blob container.

Lower band — "DATA, POLICY & CONSUMPTION"
Show governed SDMx-ML 3.0 submissions, pysdmx, BIS LBS DSD, checks_lbs.xls,
PySpark validation, Delta Lake SCD Type 2 history, Unity Catalog row filters,
column masks, quarantine, Databricks App and the public Container Apps portal.

SEQUENTIAL STAGES — render each as a numbered vertical milestone with a short
title, commands/actions, resources produced, and approximate elapsed time:

0. LOCAL & STATE BOOTSTRAP — approximately 3–8 minutes, first run only
   Actions:
   - az login and subscription selection
   - register Microsoft.Databricks, Microsoft.App,
     Microsoft.OperationalInsights, Microsoft.KeyVault,
     Microsoft.Storage and Microsoft.ManagedIdentity
   - install dependencies and run offline tests
   - create remote Terraform state resource group, storage account and tfstate
     container using Entra/RBAC authentication
   Technologies: PowerShell, Azure CLI, Python, pytest, Azure Storage, RBAC
   Gate: prerequisites valid; remote state reachable

1. TERRAFORM FOUNDATION — approximately 8–20 minutes
   Actions:
   - terraform init, validate, plan, apply
   - first-pass toggles remain false: account_groups_ready, grant_tables,
     deploy_dissemination_gateway
   Resources:
   - Entra persona groups and service principals
   - GitHub OIDC federation
   - Key Vault
   - Azure Databricks Premium workspace
   - Unity Catalog storage account, access connector, storage credential and
     external location
   - catalog dbw_sovereignshield
   - schemas sovereign_shield, sovereign_intake, sovereign_submissions
   - admin-only managed submissions volume
   - serverless SQL warehouse and cluster policy
   Technologies: Terraform, azurerm, azuread, Databricks provider, Key Vault,
   ADLS Gen2, Unity Catalog
   Gate: infrastructure outputs available

2. DATABRICKS ACCOUNT WIRING — approximately 2–5 minutes
   Actions:
   - synchronize Entra users, service principals and five account groups
   - assign groups and pipeline principal to workspace
   - re-apply Terraform with account_groups_ready=true
   Resources/permissions:
   - admin, submitter-ca, submitter-us, researchers, public
   - catalog/schema traversal and SQL warehouse CAN_USE
   Technologies: Databricks Account SCIM, Entra ID, Terraform grants
   Gate: is_account_group_member can resolve every persona

3. ASSET BUNDLE DEPLOYMENT — approximately 1–3 minutes
   Actions:
   - dot-source pre_auth.ps1
   - databricks bundle validate and deploy
   Resources:
   - three-task ingestion job
   - Databricks App definition
   - synchronized source and requirements
   Technologies: Databricks Asset Bundles, PowerShell, Azure CLI authentication
   Gate: job and app resources deployed

4. SDMx PIPELINE & POLICY PLANE — approximately 8–15 minutes including cluster start
   Show three ordered tasks:
   1) apply_security.py — idempotent DDL, policy UDFs, row filter, column mask
   2) generate_sovereign_submissions.py — synthetic sovereign microdata,
      pysdmx SDMx-ML 3.0 filings into the governed volume
   3) scd2_merge_engine.py — parse, validate checks_lbs.xls, atomic
      country-period verdict, Delta SCD2 merge
   Outcomes:
   - 22 clean baseline observations remain current and published
   - 22 revision observations are audit-only quarantine rows
   - prior accepted state remains live
   Technologies: Databricks Runtime 18.x, PySpark, Delta Lake, pysdmx,
   SDMx 3.0, BIS LBS DSD, checks_lbs.xls
   Gate: published and quarantine states verified

5. TABLE & FUNCTION GRANTS — approximately 1–3 minutes
   Actions:
   - terraform apply with grant_tables=true
   - grant SELECT on governed history and micro ledger by persona
   - grant EXECUTE on dynamic masking function
   Technologies: Terraform additive databricks_grant resources, Unity Catalog
   Gate: tables and policy functions reachable by intended identities

6. DATABRICKS APP — approximately 2–5 minutes
   Actions:
   - deploy/start sovereignshield-portal
   - add app-managed service principal to public group
   - request SQL user API scope
   - apply app CAN_USE and warehouse CAN_USE permissions
   Runtime identity:
   - signed-in user via X-Forwarded-Access-Token / on-behalf-of SQL
   - app service principal for public-tier fallback
   Technologies: Databricks Apps, FastAPI, Databricks SQL, OAuth
   Gate: app RUNNING; persona views resolve correctly

7. PUBLIC CONTAINER APPS GATEWAY — approximately 8–18 minutes
   Actions:
   - build image remotely with az acr build
   - deploy Azure Container Apps with external ingress
   - Key Vault references for the public proxy credential
   - Azure client-secret authentication to Databricks SQL
   - optional Entra Easy Auth with AllowAnonymous
   - delegated AzureDatabricks user_impersonation consent
   - login scopes: openid, profile, offline_access
   - separate Blob-backed Easy Auth token store
   - browser reads same-origin /.auth/me, keeps token in memory, sends
     Authorization: Bearer to API calls
   - restart active revision after secret updates
   Technologies: Azure Container Registry, Azure Container Apps, Easy Auth,
   Entra ID, Key Vault, Blob Storage, FastAPI
   Gate: anonymous public access plus optional signed-in persona elevation

8. PERSONA VERIFICATION & HANDOVER — approximately 5–10 minutes
   Render five compact result badges:
   - Public: 13 PUBLISHED/F observations
   - Researcher: 22 published observations, 9 values masked
   - Bank of Canada analyst: 14 observations, own restricted values visible
   - Federal Reserve analyst: 17 observations, own restricted values visible
   - Administrator: 22 published unmasked; 44 when quarantine is included
   Actions:
   - test dynamic multi-select filters and persona-scoped facets
   - test SDMX-ML, SDMX-JSON, SDMX-CSV and tidy CSV exports
   - verify no-group identity returns zero rows
   - hand over repository, Terraform examples, bundle, skills, runbooks,
     architecture diagrams and whitepaper — never tfvars, backend.hcl, state or
     credentials
   Technologies: Unity Catalog RLS/DDM, FastAPI portal, SDMx exports, Git
   Gate: client acceptance and controlled builder revocation

FINAL HANDOVER PANEL — far right
Show a shielded repository package crossing into a client-owned boundary.
Labels:
- "Specification in"
- "Synthetic proof"
- "Client-owned deployment"
- "Builder access revoked"
- "No production data transferred"

BOTTOM TIMELINE:
Show approximate elapsed time under each stage and a total first-run range of
approximately 30–70 minutes, with a note:
"Cloud provisioning, cluster start, RBAC propagation and ACR build times vary by
region, quota and first-run extension installation. Re-runs are materially faster."

SIDE LEGEND — "OWNERSHIP"
- Terraform: infrastructure and access-control plane
- Databricks Asset Bundles + SQL: data and policy plane
- Unity Catalog: query-time enforcement
- Client administrators: account identities, approvals and final ownership

SIDE LEGEND — "SECURITY INVARIANTS"
- USER_ISOLATION compute
- No credential literals in tracked source or Terraform variables
- Public is an explicit identity, not a fall-through
- No recognised group = zero rows
- Quarantined revision never replaces published state
- One writer per object

FOOTER:
"Approximate timings for an evaluation deployment · Independent reference
architecture · Synthetic data · Not affiliated with or endorsed by any central
bank, international organisation or technology vendor"

OUTPUT REQUIREMENTS:
- 3840×2160 landscape.
- Every stage number, duration, command family, technology and gate must be
  readable and correctly spelled.
- Use arrows only for real dependencies; show the three deferred Terraform
  applies as explicit gates, not as one monolithic apply.
- Make the sequential story dominant and the technology inventory secondary.
- Do not invent products, steps, timings or data flows beyond those specified.
```

---

## Executive prompt

```text
Create a polished 16:9 enterprise keynote graphic explaining a data governance
platform for INTERNATIONAL STATISTICAL REPORTING — the submission of confidential
national banking statistics to an international standards body.

STYLE: Premium corporate, clean and confident, suitable for a board presentation.
Light background: soft white on the left blending to pale ice-blue on the right.
Subtle reflective floor, gentle depth. Flat vector illustration with soft
shadows. No photorealism. Muted institutional palette: deep navy, slate grey,
teal accent, warm amber for the one warning element.

CRITICAL CONSTRAINTS — follow exactly:
- Do NOT draw any company logo, brand mark, product icon or trademark.
- Do NOT draw national flags, country outlines, maps, or recognisable
  government or central-bank buildings.
- Do NOT invent institution names. The only text is what is specified below.
- Represent organisations as neutral abstract shapes only.

COMPOSITION: a single left-to-right narrative along a softly glowing horizontal
pathway, in four zones.

ZONE 1 — FAR LEFT, "REPORTING JURISDICTIONS". Three identical simple hexagonal
tiles stacked vertically, each a different muted colour (slate blue, muted teal,
warm grey), each bearing only a two-letter abstract placeholder in clean sans
type: "AA", "BB", "CC". No flags. From each tile a crisp white document glyph
marked with angle brackets < > drifts rightward and merges onto the pathway.
Label beneath the group: "REPORTING JURISDICTIONS". Label on the document
stream: "STANDARDISED SUBMISSIONS".

ZONE 2 — LEFT-CENTRE, "AUTOMATED VALIDATION". A tall translucent glass gate
across the pathway. Most documents pass through and continue. ONE document is
deflected downward into a small amber-outlined tray beneath the pathway, marked
with a clean pause symbol. Label above the gate: "AUTOMATED RULE CHECK". Label
on the amber tray: "HELD FOR CORRECTION". A thin caption beneath: "One
jurisdiction's error never blocks another's".

ZONE 3 — CENTRE, "THE GOVERNED VAULT". The visual anchor: a large softly glowing
translucent cylinder standing on the pathway, deep navy with an inner teal light.
Wrapped around it, three concentric rings, each a different tone, each labelled
in small clean type on the ring itself:
  inner ring  — "WHO YOU ARE"
  middle ring — "WHAT YOU MAY SEE"
  outer ring  — "WHAT IS PUBLISHED"
Label beneath the cylinder: "POLICY ENFORCED AT THE DATA, NOT IN THE APPLICATION".

ZONE 4 — RIGHT, "FOUR AUDIENCES, ONE SOURCE". Four simple abstract human
silhouettes in a row, each standing on a small white pedestal, each connected
back to the cylinder by a distinct coloured beam. Beside each figure a compact
card with a title and one short line:

  Figure 1, grey beam, card: "PUBLIC" / "Published figures only"
  Figure 2, indigo beam, card: "RESEARCHER" / "All published data, sensitive
    values hidden"
  Figure 3, teal beam, card: "NATIONAL ANALYST" / "Own jurisdiction in full"
  Figure 4, deep red beam, card: "AUDITOR" / "Complete view, fully accountable"

Show the beams as visibly different widths — narrowest to the PUBLIC figure,
widest to the AUDITOR figure — so the graduation of access is obvious at a glance.

TITLE, top-left, large and confident:
  "Sovereignty as a Platform Guarantee"
SUBTITLE, directly beneath, smaller:
  "Confidential statistical exchange, governed at the data layer"

FOOTER, bottom edge, small but clearly legible, in neutral grey:
  "Independent reference architecture · Illustrative synthetic data · Not
  affiliated with or endorsed by any central bank or international organisation"

Balanced composition, generous white space, no clutter. Every label must be
crisp and correctly spelled.
```

---

## Technical prompt

```text
Create a detailed 16:9 technical architecture diagram for a Zero-Trust data
governance platform handling confidential statistical submissions.

STYLE: Dark-mode engineering blueprint. Deep charcoal-navy background (#0b1f33)
with a faint grid. Crisp flat vector, thin bright strokes, subtle outer glow on
active paths. Palette: cyan for control plane, teal for data plane, amber for
quarantine, magenta for identity, muted grey for inert. Monospace-style labels.
Precise and legible over decorative — this is read closely, not glanced at.

CRITICAL CONSTRAINTS — follow exactly:
- Do NOT draw any company logo, brand mark, product icon or trademark.
- Do NOT draw national flags, country outlines or maps.
- Vendor and product names appear ONLY as plain typeset text labels.
- Every label must be crisp and correctly spelled.

LAYOUT: four stacked horizontal bands, plus a vertical enforcement column on the
right that all bands connect into.

BAND 1 (top) — "PROMOTION PLANE", cyan.
Left to right, five rounded rectangles joined by arrows:
  "PULL REQUEST" -> "OFFLINE TESTS" -> "REVIEW" -> "MERGE" -> "OIDC TOKEN"
Beneath "OFFLINE TESTS", a small caption: "no credentials required".
From "OIDC TOKEN" two arrows fan downward and to the right, one labelled
"TERRAFORM", the other labelled "ASSET BUNDLE".
A small padlock glyph on the OIDC arrow with the caption:
  "short-lived · no stored secret"

BAND 2 — "OWNERSHIP BOUNDARY", split into two clearly separated panels with a
bold vertical dashed divider between them and the words "ONE WRITER PER OBJECT"
printed vertically along the divider.

  LEFT PANEL, magenta border, heading "TERRAFORM — INFRASTRUCTURE & ACCESS":
    a bulleted list in small mono type:
      "identity groups · service principals"
      "key vault · federated credentials"
      "workspace · storage credential"
      "catalog · schema · warehouse"
      "GRANT usage / select"

  RIGHT PANEL, teal border, heading "PIPELINE — DATA & POLICY":
    "table DDL"
    "row filter function"
    "column mask function"
    "SET ROW FILTER / SET MASK"
    "published view"

  Beneath the divider, a small amber caption:
    "grants decide reachability · filters decide visibility"

BAND 3 — "DATA PLANE", teal.
Left to right:
  A stack of three small document glyphs marked < > labelled "SUBMISSIONS (SYNTHETIC)".
  Arrow into a hexagon labelled "RULE ENGINE" with a sub-caption
    "checks parsed at runtime".
  Two arrows leave the hexagon:
    upper arrow, teal, labelled "PASS" into a cylinder labelled "HISTORY TABLE"
    lower arrow, amber, labelled "FAIL -> QUARANTINE" into a smaller amber-outlined
      box labelled "AUDIT ONLY · NOT CURRENT"
  A curved amber arrow loops from the quarantine box back beneath the cylinder,
  labelled: "prior published record stays live".
  Beneath the cylinder, small mono text: "SCD2 · valid_from · valid_to · is_current".

BAND 4 (bottom) — "CONSUMPTION", grey to teal.
Left to right: a rounded box labelled "DISSEMINATION GATEWAY" with two stacked
sub-labels inside: "anonymous -> proxy identity" and "signed-in -> caller token".
An arrow leaves it heading right into the enforcement column.
A small caption beneath the gateway, in bright cyan:
  "chooses an identity · never chooses rows"

RIGHT VERTICAL COLUMN — "POLICY ENFORCEMENT POINT".
A tall narrow glowing panel running the full height of bands 2 to 4, bright cyan
border, containing top to bottom:
  heading "UNITY CATALOG"
  "fn_rls_multi_persona_lock"
  "  (key, batch_status, confidentiality)"
  "fn_ddm_confidentiality_mask"
  "  (value, confidentiality, key)"
  a thin divider
  then five small rows, each a coloured dot with a label and a short outcome:
    grey dot    "PUBLIC"      "published + free only"
    indigo dot  "RESEARCHER"  "published · values masked"
    teal dot    "SUBMITTER"   "own jurisdiction in full"
    red dot     "AUDITOR"     "unrestricted"
    hollow dot  "NO GROUP"    "zero rows — fails closed"
  The "NO GROUP" row is drawn dimmer than the others with a small X glyph.

TITLE, top-left, bold:
  "Policy as a Metastore Object"
SUBTITLE beneath:
  "Entitlement evaluated per caller, per row, at query time"

BOTTOM-RIGHT technology strip, small plain grey typeset text on one line:
  "Azure Databricks · Unity Catalog · Delta Lake · Microsoft Entra ID · Terraform · SDMX 3.0"

FOOTER, bottom edge, small neutral grey:
  "Independent reference architecture · Illustrative synthetic data · Not
  affiliated with or endorsed by any central bank or international organisation"

Dense but organised. Clear separation between bands. Nothing overlapping.
```

---

## Adaptation notes

**Executive prompt**

* **Board or regulator audience** — enlarge the footer disclaimer and repeat it
  verbally in the first fifteen seconds.
* **Naming the vendors** — to show the technology stack, add one neutral typeset
  line beneath the footer: *"Built on Azure Databricks and Microsoft Entra ID."*
  Typeset text is nominative use; a rendered logo is not.
* **Real jurisdictions** — substitute real ISO codes in Zone 1 only after
  confirming that no institutional affiliation is implied. The abstract
  placeholders exist to make that a conscious decision rather than a default.

**Technical prompt**

* **Security review** — enlarge the right-hand enforcement column to half the
  canvas and drop Band 1; the promotion story is rarely what that audience is
  probing.
* **Platform-team onboarding** — keep all four bands and add a fifth strip naming
  the actual repository files under each band, so the diagram doubles as a map.
* **Real function names** — the prompt uses shortened names for legibility. The
  real names are `fn_rls_multi_persona_lock` and `fn_ddm_obs_conf_mask`; image
  models truncate strings that long, so substitute them only when hand-editing
  the output afterwards.
