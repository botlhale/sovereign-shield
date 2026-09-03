# Technical Vision — Image Prompt

**Audience:** architects, security advisors, platform engineers, technical review boards
**Use:** one dense diagram to anchor a design discussion or architecture review
**Companion:** [`executive_vision.md`](executive_vision.md) for the SLT version

---

## Design intent

This image has to survive being *interrogated*. An architect will ask "where is
the policy actually evaluated?" and "what stops the pipeline and Terraform
fighting?" — so the diagram carries the two ownership boundaries and the
enforcement point explicitly, rather than hiding them behind a generic "governance"
box.

Same legal constraints as the executive version: no vendor logos, no flags, no
implied affiliation, visible synthetic-data caption. Vendors appear as typeset
text because architects need the stack named, which is nominative use rather than
brand reproduction.

**Not legal advice.** Route external material through your usual reviewer.

---

## The prompt

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

## Talking points the diagram is built to support

Each maps to something visible, so you can point rather than assert.

### "Where is policy actually evaluated?"

*Right-hand column.* Not in the gateway, not in the pipeline, not in the BI tool
— in the metastore, per caller, per row, at query time. That is why the same
entitlement holds across a notebook, a SQL warehouse, a dashboard and the public
API without being re-implemented four times.

The gateway's caption is the load-bearing claim: **it chooses an identity, never
chooses rows.** Compromise it entirely and the metastore still refuses.

### "What stops Terraform and the pipeline fighting?"

*Band 2, the dashed divider.* Row filters are detached and re-attached on every
pipeline run so the functions they bind can be replaced. If Terraform also owned
them it would report drift after every run, and an apply could detach a live
filter mid-query.

Grants are additive, never authoritative — an authoritative grant resource
revokes anything it does not declare, which would silently strip whatever the
other path granted.

### "What happens when a submission fails validation?"

*Band 3, the amber loop.* The failed batch is written as an audit record and
marked not-current. The previously published figure **stays live**. Validation
failure degrades to stale data, never to missing data.

Quarantine is atomic per jurisdiction-period: publishing only the passing subset
would emit an internally contradictory dataset, because the totals that reconcile
depend on the components that did not.

### "How do you off-board someone?"

*Bottom row of the enforcement column.* Remove them from the groups. No
membership resolves to zero rows — not an error, not a partial view. The
mechanism that separates two jurisdictions is the mechanism that removes a
departing contractor. There is no second revocation path to forget or under-test.

### "How was this built without the data?"

*Band 1.* The offline test suite runs with no credentials at all. The specialist
develops against generated submissions and a local mirror of the policy, opens a
pull request, and never deploys. Promotion is a federated identity that only a
merged commit can assume.

---

## Anticipated challenges

Worth rehearsing — an architecture review will find these.

| Challenge | Honest answer |
| --- | --- |
| "The local policy mirror duplicates the SQL. That will drift." | It will. The offline tests assert the same expectations the live tests assert against the real metastore, so drift fails the live run. It is a verified convenience, not an independent implementation to trust. |
| "Views resolve group membership as the view owner." | Correct, which is why the gateway queries the base table directly. A pre-filtered view would hand every visitor the owner's entitlement. |
| "A row filter that raises kills the whole table." | Yes. That is why the segment lookup is the non-throwing variant wrapped in a coalesce to false. A malformed key becomes invisible rather than causing an outage. |
| "Ownership must exempt the pipeline principal." | It does not. Object ownership does not lift a row filter — the pipeline identity has to hold the admin persona explicitly, or its merge reads an empty target and silently duplicates history. |
| "Account-scope vs workspace-scope groups." | Only account-scope groups resolve. Workspace-scoped groups of the same name look identical in the console and match nothing. This is the most common misconfiguration and it fails closed. |
| "Synthetic data proves nothing about scale." | Agreed. Volumetrics, skew and cost at real volume need a production dry-run. This demonstrates correctness of the control model, not performance. |

---

## Adaptation notes

* **Security review** — enlarge the right-hand enforcement column to half the
  canvas and drop Band 1; the promotion story is rarely what that audience is
  probing.
* **Platform-team onboarding** — keep all four bands and add a fifth strip naming
  the actual repository files under each band, so the diagram doubles as a map.
* **Substituting real function names** — the prompt uses shortened names for
  legibility. Real names are `fn_rls_lbs_multi_persona_lock` and
  `fn_ddm_obs_conf_mask`; image models truncate strings that long, so replace
  them only if you intend to hand-edit the output afterwards.
