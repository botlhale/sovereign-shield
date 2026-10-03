# Image-Generation Prompts

Production-ready prompts for generating presentation artwork with Gemini image models.
The hand-authored [publication figures](README.md) and the Mermaid
[architecture diagrams](../ARCHITECTURE_DIAGRAMS.md) remain the architectural authority.
A generated image is an illustration: publish it only after every label and arrow passes
the checks below, and caption it as AI-generated.

## Choosing a Model

Model names change quickly; confirm the current tier names in Google AI Studio or Vertex AI
before a run. The guidance below is by capability tier.

| Tier | Example model | Use for | Avoid for |
| --- | --- | --- | --- |
| **Gemini Pro image** | Gemini 3 Pro Image ("Nano Banana Pro") | Final labelled diagrams: layout reasoning, legible text, 2K-4K output, reference images for a consistent style | Fast exploration; it is slower and costs more per image |
| **Gemini Flash image** | Gemini 2.5 Flash Image | Drafts: composition, palette, iconography and conversational edits before the final Pro render | Dense labels; small text degrades |
| **Imagen** | Imagen 3 or 4 | Label-free hero art, such as a LinkedIn banner background | Any image whose meaning depends on exact text or arrows |

Recommended routing: draft prompts C and D in Flash, then render all six prompts and the
engagement figures in Pro. Request 16:9 at the highest native size (Pro returns 2752x1536 at
2K; ask for 4K where offered) and check the downloaded dimensions. Upscaling does not repair
small text.

## Shared Style and Negative Prompt

Append both blocks to every prompt. They match the slate, teal, indigo and sky palette of the
publication figures, so generated and hand-authored images sit together in one deck.

```text
STYLE: minimal enterprise vector illustration with subtle 3D isometric depth. Deep slate
background #0F172A to #1E293B. Planes as rounded cards with 1-2 px borders and soft shadows.
Accent colours: teal #0F766E (governance), indigo #4338CA (serving and provider work),
sky #0369A1 (persona outputs), amber #F59E0B only for risks and limits. Text #F8FAFC in a
clean geometric sans-serif such as Inter; monospace only for SDMx keys. Large readable
labels, generous spacing, orthogonal arrows with clear heads, at most 12 words per card.
Flat icons only: shield, database cylinder, document, person silhouette, key.

NEGATIVE: no garbled, misspelled, mirrored or invented text; no pseudo-text or lorem ipsum;
no labels beyond those specified; no rendering of these instructions, IDs or colour names as
text; no logos, trademarks, flags or institution names; no faces or photographs; no messy,
grainy, painterly or noisy textures; no neon glow, lens flare or circuit-board backgrounds;
no padlock clutter; no arrows without heads, through cards or crossing without a bridge;
no tiny text; no watermark.
```

## Prompts

Each prompt fixes the visible text verbatim. Do not ask the model to invent labels.

### A. The Contractor Dilemma

Pro. The boundary is production isolation, not an air gap: never label it "air-gapped".

```text
Create a 16:9 two-zone architecture illustration titled "The Contractor Dilemma: Build
Without Seeing".

LEFT ZONE, indigo border, label "Provider and AI-agent sandbox · synthetic only". Three
stacked cards: "Approved DSD, codelists and rules", "Synthetic SDMx fixtures",
"Code, policies and credential-free tests".
RIGHT ZONE, teal border, label "Client sovereign boundary". Cards: "Independent review",
"Synthetic staging", an amber diamond "Production approval", then "Production SDMx intake ·
same policies". A slate database cylinder "Confidential filings" connects only to the
production card.
BETWEEN THE ZONES: a vertical dashed boundary labelled "Contract boundary". One thick arrow
crosses it from left to right, labelled "Reviewed code, tests, evidence". One thin arrow
crosses from right to left, labelled "Approved metadata". Draw a small amber "no entry"
marker on the boundary beside the cylinder with the label "Data never crosses".
FOOTER: "Production-isolated delivery. The client owns identities, data and release."
```

### B. Triple-Lock Security

Pro. Storage isolation is the foundation; the three locks are the repository's controls.

```text
Create a 16:9 layered isometric stack titled "Triple-Lock Security on Unity Catalog".
Bottom to top, four slabs:
1. Slate slab "Foundation · storage isolation": "Admin-only filing archive",
   "Separate intake schema", "Managed-identity storage credential".
2. Teal slab "Lock 1 · Row filter": "Rows by country, lifecycle and confidentiality".
3. Teal slab "Lock 2 · Column masks": three chips "Value → restricted",
   "Key → Q.S.C.A.USD.D.5J.A.US.xx.xx", "Lineage hashes → NULL".
4. Teal slab "Lock 3 · Publication state": "PUBLISHED and current only".
Left of the stack, one indigo card "Query from portal, API or SQL" with an arrow entering the
top slab. Right of the stack, four sky output cards with arrows leaving the stack:
"Public: free values", "Researcher: discovers, cannot read", "Submitter: own data in full",
"Administrator: full audit".
AMBER NOTE at the bottom: "Entitlement is not disclosure control. Published margins can
still isolate a cell."
```

### C. Submission History on Two Timelines

Flash draft, Pro final. The history intervals use receiver time; the second axis is the
sender's submission time. Do not label it "fully bi-temporal".

```text
Create a 16:9 timeline diagram titled "One Atomic Transition per Filing".
SUBTITLE: "Scope: CA · 2026-Q1 · LBSR".
Two horizontal axes: top axis "Sender submitted-at", bottom axis "Receiver received-at
(history time)". Thin dotted connectors join each filing's two timestamps.
Four filings left to right:
1. Teal bar "Filing A accepted: keys A, B" from its received time to the next acceptance,
   then closed.
2. Amber marker "Filing R rejected · audit only" with a short closed bar; current data
   unchanged.
3. Teal bar "Filing B accepted: key A only" open to the right edge with "VALID_TO = NULL";
   a small label on the end of A's bars: "Closed in the same MERGE".
4. Grey marker "Late older filing · audit only", whose sender time is earlier than B's.
Right panel, sky card "Analyst View": "Expected latest filing vs receiver state:
IDs, times, values, verdict".
FOOTER: "Replay of the same message adds nothing. A new identical filing is kept."
```

### D. Three Consumption Planes

Flash draft, Pro final. The enclave is a concept: draw it dashed.

```text
Create a 16:9 hub diagram titled "One Governed Store, Three Consumption Planes".
CENTRE: a teal shield-shaped hub "Unity Catalog governed history".
LEFT, sky panel "Public dissemination": "Releasable SDMx-ML, JSON and CSV",
"Researchers download the public file".
TOP RIGHT, indigo panel "Discovery Gateway": "Restricted series exist ·
key …US.xx.xx · value restricted". From it, a dashed arrow to a dashed-outline panel
"Secure Data Enclave (concept)": "Approved researchers · regressions on restricted
cells · no raw export".
BOTTOM RIGHT, slate panel "Audit oversight": "Administrator lifecycle audit",
"Submitter Analyst View".
Solid arrows from the hub to each solid panel; no arrow from the hub to the enclave.
FOOTER: "The enclave is a policy concept, not deployed infrastructure."
```

### E. Complete Technical Architecture

Pro. Use the [executive architecture figure](executive_architecture.png) as a style
reference image, not as a layout to copy.

```text
Create a 16:9 technical architecture titled "Sovereign Shield: Governed SDMx Exchange on
Azure Databricks", organised as four vertical planes left to right, each a rounded column:
1. Slate "Intake perimeter": "SDMx-ML 3.0 filings", "Pinned BIS LBS 1.0 · 21 rules",
   "Delta history · one MERGE per filing", "Admin-only archive volume".
2. Teal "Governance plane · Unity Catalog": "Row filter", "Value mask",
   "Coordinate mask xx.xx", "Lineage mask", "Account groups".
3. Indigo "Trusted serving plane": "Databricks App · SSO", "Container Apps · anonymous +
   Easy Auth", "FastAPI gateway · identity, filters, lifecycle", "SDMx exports via pysdmx".
4. Sky "Persona outputs": "Public", "Researcher · Discovery Gateway", "Submitter · Analyst
   View", "Administrator · audit".
Under the planes, a thin slate band "Terraform · Asset Bundles · Key Vault · OIDC CI".
Arrows: plane 1 → 2 "governed table"; plane 2 → 3 "resolved per caller";
plane 3 → 4 "entitled rows".
FOOTER: "Synthetic data. Independent reference architecture."
```

### F. Executive Architecture

Pro. Executives read outcomes, not components: keep it to four personas and one store.

```text
Create a clean 16:9 executive illustration titled "Four Audiences, One Governed Source".
SUBTITLE: "Built on synthetic data; enforced in production without code changes".
CENTRE: a large teal isometric shield over a database labelled "One governed statistical
store".
LEFT: an indigo card "External builders and AI agents" with a small badge "synthetic only",
an arrow into the shield labelled "Reviewed code".
RIGHT: four sky persona cards with arrows from the shield:
"Public · published free values", "Researchers · discover restricted series",
"Submitting central banks · own data, filing status", "Administrators · full audit".
BOTTOM: three outcome chips: "No production access to build", "One policy set, every
channel", "Every filing auditable".
AMBER NOTE, bottom right, small: "Statistical disclosure review remains a release decision."
```

## Engagement Figures

Two engagement figures were specified for the [engagement playbook](../ENTERPRISE_ONBOARDING_PLAYBOOK.md).
Hand-authored 3840x2160 versions with editable SVG sources are in the
[review gallery](review/README.md) and remain the reference. Generate each figure in its own
Pro request; never compress both into one image.

### Figure A: Engagement Control Flow

```text
Draw an enterprise swimlane diagram on a clean white canvas with charcoal text, a pale teal
provider lane, a pale blue client-operations lane and amber approval diamonds. Flat shapes,
orthogonal connectors, generous margins, 16:9.

TITLE: "SovereignShield: Nature of Engagement and Handover"
SUBTITLE: "Synthetic-first development; client-controlled production"

Seven columns with one header each: 1 Agree | 2 Establish | 3 Build and test | 4 Review |
5 Hand over | 6 Accept and deploy | 7 Operate and exit.
Three lanes: A "Client sponsor, data authority and review"; B "External technical provider";
C "Client platform and operations". Lane B holds synthetic development only.

Nodes (IDs are instructions, never print them):
A1 lane A col 1 "Scope and SDMx contract"; G1 lane A col 1 diamond "Approve synthetic
development"; B1 lane B col 2 "Approved repository / Synthetic-only development";
C1 lane C col 2 "Client sandbox / Time-bounded access"; B2 lane B col 3 "Build, test and
submit PR"; A2 lane A col 4 "Independent security and disclosure review"; G2 lane A col 4
diamond "Accept release and residual risks"; B3 lane B col 5 "Versioned handover package";
C2 lane C col 5 "Import approved release"; C3 lane C col 5 "Client identities, vault and
state"; C4 lane C col 6 "Synthetic staging acceptance"; G3 lane A col 6 diamond "Production
and disclosure approval"; C5 lane C col 6 "Client production deployment"; C6 lane C col 7
"Operate and reconcile"; C7 lane C col 7 "Offboard provider"; C8 lane C col 7 "Verify
runtime continuity".

Solid arrows only: A1→G1; G1→B1 "Approved scope"; G1→C1 "Approved sandbox"; B1→B2; B2→A2;
A2→G2; G2→B3 "Approved"; B3→C2 "Reviewed artifacts"; C2→C3; C3→C4; C4→G3 "Acceptance
evidence"; G3→C5 "Approved"; C5→C6; C6→C7 "Handover accepted"; C7→C8.
Dashed arrows only: C1→B1 "Optional sandbox access"; G2→B2 "Rework findings";
G3→C4 "Rework findings". No other arrows.

Enclose C4-C8 in a box "Client-controlled staging and production" inside lane C only.
LEGEND: "Solid: workflow or approved handoff · Dashed: optional access or rework ·
Diamond: client approval · Lane: accountable owner".
FOOTER: "Independent reference architecture; no institutional or vendor endorsement."
```

### Figure B: Submission and Analyst Reconciliation

```text
Draw a 16:9 information-flow diagram in the same white, charcoal and restrained teal/blue
style. No phase headers, diamonds or provider lane.

TITLE: "SovereignShield: Submission and Analyst Reconciliation"
SUBTITLE: "Latest submitted is distinct from current accepted publication"

Left box "Reporting authority" containing S1 "Reporting authority / SDMx submission" and
S8 "Sender's expected filing evidence". Right enclosure "Client-controlled service"
containing S2 "Approved SDMx file intake", S3 "Protected archive and validation",
S4 "Governed submission history", S5 "Current accepted publication",
S6 "Restricted submission / quarantine audit" and S7 "Analyst reconciliation / Expected
filing versus receiver state". Place S5 and S6 side by side.

Arrows only: S1→S2 "SDMx files only" (it must start at S1, not S8); S2→S3;
S3→S4 "Validated outcome and submission identity"; S4→S5 "Current accepted selection";
S4→S6 "Authorized audit selection"; S5→S7 "Entitled current data";
S6→S7 "Own-country submission feedback"; S8→S7 "Expected ID, values and submission time".
S7 only consumes: no arrow leaves S7.

Annotation beside S7: "Compare IDs, submitted/received times, values and validation outcome."
Annotation below S4: "Rejected arrivals do not replace current accepted data."
A small amber-tinted note with no arrows: "Disclosure review: public totals and row
presence can reveal masked values." Render the note text only; never print the word "amber".
FOOTER: "Processing timestamps are not attested transport receipts."
```

## Review Before Publication

| Check | Pass condition |
| --- | --- |
| Text | Every label matches the prompt verbatim; no invented, misspelled or leaked instruction text |
| Topology | Every arrow matches the allowed list; no arrow from a consumer back to a producer |
| Ownership | Confidential data, intake and operations sit only in client-owned areas |
| Claims | No "air-gapped", "guarantee", "unhackable" or certification wording; the enclave is marked as a concept |
| Legibility | Text readable at slide size and on a phone; dimensions as requested |
| Provenance | Model, date, prompt section and reviewer recorded; caption states "AI-generated illustration" |

Correct a misplaced node by naming the node and its permitted connection in a follow-up edit.
For persistent text or topology errors, redraw in an editable SVG instead.

## Assessment of Existing Renders

Six Gemini renders were reviewed on 1 October 2026 from a local, uncommitted working folder.
None is committed or used in a publication; regenerate with the prompts above.

| Render | Strength | Blocking issue |
| --- | --- | --- |
| Executive overview ("Sovereignty as a Platform Guarantee") | Clean, readable persona story | "Guarantee" overclaims; no Discovery Gateway or coordinate masking |
| Technical vision (blueprint style) | Strong plane structure | Names a non-existent function `fn_ddm_confidentiality_mask`; no coordinate or lineage masks |
| Lifecycle poster | Complete stage sequence | Too dense for slides; reference only |
| First engagement flow | Restrained palette | Confidential data and intake drawn in the provider lane; a staging-to-production bypass |
| Engagement Figure A | Correct columns, gates and legend | "Operate and reconcile" placed in the provider lane; the production boundary crosses it |
| Analyst reconciliation Figure B | Faithful products and annotations | "SDMx files only" starts at the sender evidence box; the instruction word "Amber" is printed |
