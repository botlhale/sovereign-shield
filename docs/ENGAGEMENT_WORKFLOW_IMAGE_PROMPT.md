# Engagement Workflow Diagram Prompt

**Purpose:** a professional enterprise architecture diagram accompanying
[Nature of Engagement and Handover](ENTERPRISE_ONBOARDING_PLAYBOOK.md). The workflow
specification and renderable Mermaid remain authoritative if generated labels or
arrows differ. Verify every label and connection before publication.

Editable SVGs and 3840x2160 PNGs for both revised figures are available in the
[review gallery](figures/review/README.md). These are manually laid out review
assets, not approved replacements for the current publication images.

## Assessment of the First Gemini Pro Rendering

**Disposition:** suitable for concept discussion after explanation, not ready as
an authoritative architecture or stakeholder handover diagram.

The supplied image preserves the title, restrained palette, three participant
lanes, seven phase labels and important disclosure/continuity concepts. Several
connectors and placements change the meaning of the workflow:

| Priority | Observed Issue | Required Correction |
| --- | --- | --- |
| Critical | `Client confidential data` and `Approved SDMx file intake` occupy the External Technical Provider lane | All confidential records, intake and production operations must stay visibly inside the client boundary |
| Critical | A direct staging-to-production arrow bypasses approval; production/disclosure approval appears twice | Show one production approval diamond, with every promotion path passing through it |
| High | Build/tests connect directly to client import, while the approved-version gate mainly routes back to tests | Approved release must precede handover and client import; rejection feedback is a separate labelled path |
| High | The Analyst View points toward the publication/audit boxes as if it creates them | Governed history supplies distinct products; the Analyst View consumes entitled results and sender evidence |
| High | Provider offboarding is placed in the provider lane and points toward operations; the final feedback loop reaches the sandbox | Client operators own revocation after operational handover; feedback is approved findings, never production data or a runtime dependency |
| Medium | Phase headings repeat inside the grid and nodes drift under the wrong phase | One header per phase and one assigned lane/column per node |
| Medium | Dense small labels, ambiguous crossings and the literal instruction `Bank micro-transactions not shown` reduce clarity | Reduce text, separate workflow from data flow, and never render instructions as labels |

This is evidence about this rendering, not a general performance claim about all
Gemini versions. The first prompt mixed placement guidance, long explanatory
labels and several kinds of arrows. The revised prompts use a finite node table,
explicit allowed edges and separate diagrams for engagement control flow and
production information flow. A model self-check does not replace human inspection.

## Gemini Pro Generation Method

1. Generate **Figure A only** first. Use the previous image as a style reference,
   not as a topology to preserve. Request a fresh redraw rather than a cosmetic edit.
2. Supply only the Figure A prompt below, keeping its fixed node list and connectors.
   Do not append the entire playbook. Inspect ownership and gate order before style.
3. Generate Figure B in a separate request with the same visual style. Do not
   compress the two specifications into one 16:9 image.
4. Request 3840x2160 where the selected Gemini image model supports it, or its highest
   native output resolution. Confirm the downloaded dimensions; a prompt asking for
   4K does not prove that the supplied preview or file is 4K. Do not repair tiny text
   by upscaling alone.
5. Correct a misplaced node or edge by naming its ID and permitted connection.
   For final publication, reconstruct persistent topology or typography errors in
   a diagram editor using the same node/edge specification. Preserve editable source.

## Figure A Prompt: Engagement Control Flow

```text
Redraw an enterprise engagement diagram from the specification below. If a previous
image is attached, reuse only its white background and restrained teal/blue/amber
palette. Do not preserve its node positions or arrows.

Priority order: correct ownership; correct approval sequence; readable text; style.
Produce one 16:9 landscape image, preferably 3840x2160 if supported. Use a clean
white canvas, charcoal text, pale teal provider lane, pale blue client-operations
lane and amber approval diamonds. Use flat rectangular nodes, consistent typography,
orthogonal connectors and generous margins. No gradients, 3D effects or logos.

RENDER THIS TITLE:
SovereignShield: Nature of Engagement and Handover
RENDER THIS SUBTITLE:
Synthetic-first development; client-controlled production

LAYOUT - instructions, not visible text:
Use a fixed seven-column, three-swimlane grid. Exactly one phase header per column:
1 Agree | 2 Establish | 3 Build and test | 4 Review | 5 Hand over |
6 Accept and deploy | 7 Operate and exit
Do not repeat phase headers within any lane. Keep every node fully inside its
assigned column and lane. Use a wider left margin for horizontal lane labels:
A: Client sponsor, data authority and review
B: External technical provider
C: Client platform and operations
Keep A and C visibly client-owned. Lane B contains synthetic-only development
artifacts. No confidential data, production intake or revocation authority in B.

VISIBLE NODES - IDs are instructions only; do not print IDs:
A1 | lane A, column 1 | rectangle | Scope and SDMx contract
G1 | lane A, column 1, below A1 | diamond | Approve synthetic development
B1 | lane B, column 2 | rectangle | Approved repository / Synthetic-only development
C1 | lane C, column 2 | rectangle | Client sandbox / Time-bounded access
B2 | lane B, column 3 | rectangle | Build, test and submit PR
A2 | lane A, column 4 | rectangle | Independent security and disclosure review
G2 | lane A, column 4, below A2 | diamond | Accept release and residual risks
B3 | lane B, column 5 | rectangle | Versioned handover package
C2 | lane C, column 5, upper | rectangle | Import approved release
C3 | lane C, column 5, lower | rectangle | Client identities, vault and state
C4 | lane C, column 6, upper | rectangle | Synthetic staging acceptance
G3 | lane A, column 6 | diamond | Production and disclosure approval
C5 | lane C, column 6, lower | rectangle | Client production deployment
C6 | lane C, column 7, upper | rectangle | Operate and reconcile
C7 | lane C, column 7, middle | rectangle | Offboard provider
C8 | lane C, column 7, lower | rectangle | Verify runtime continuity

Use two or three readable lines per node. A slash indicates a line break, not
literal punctuation to print. Do not add explanatory paragraphs inside nodes.
Exactly three diamonds exist: G1, G2 and G3. G3 appears once only.

EXACT SOLID CONNECTORS - ordered workflow or artifact handoff, not data flow:
A1 -> G1
G1 -> B1, label: Approved scope
G1 -> C1, label: Approved sandbox
B1 -> B2
B2 -> A2
A2 -> G2
G2 -> B3, label: Approved
B3 -> C2, label: Reviewed artifacts
C2 -> C3
C3 -> C4
C4 -> G3, label: Acceptance evidence
G3 -> C5, label: Approved
C5 -> C6
C6 -> C7, label: Handover accepted
C7 -> C8

EXACT DASHED CONNECTORS:
C1 -> B1, label: Optional sandbox access
G2 -> B2, label: Rework findings
G3 -> C4, label: Rework findings

No other connectors. In particular, no B2 -> C2, B2 -> C5, C4 -> C5,
G2 -> C5, C8 -> C1 or production-to-provider feedback loop.
Route C4 -> G3 and G3 -> C5 in separate vertical gutters within column 6.
Crossing a lane with a connector does not transfer ownership of its endpoint.
Use visible arrowheads. No arrow through a node, no ambiguous junction and no
double-headed arrow. A line crossing without a connection uses a bridge.

BOUNDARIES:
Enclose C4, C5, C6, C7 and C8 in a labelled client-controlled staging/production
boundary entirely within lane C, columns 6-7. Keep G3 in the client review lane.
Do not extend that enclosure through the provider lane. Do not confuse a dashed
enclosure with a feedback arrow.

VISIBLE LEGEND:
Solid arrow: workflow / approved artifact handoff
Dashed arrow: optional access or rework
Diamond: client approval
Swimlane: accountable owner

VISIBLE FOOTER:
Independent reference architecture; no institutional or vendor endorsement.
Production administration and acceptance remain client-owned.

Do not draw confidential-data cylinders or publication/audit data products in
this figure; those belong in the separate production-information figure.
Do not render negative instructions such as "not shown". Do not add extra phase
labels, side panels, cost strips, portability lists or decorative shapes. Leave
space around each label; shorten line breaks, not the specified meaning.

Before returning the image, check node ownership against the table and every
arrow against the allowed connectors. Every route into C5 must pass G3. Every
route into C2 must pass G2 and B3. Offboarding is client-owned and follows
operational handover. Do not print this checklist on the image.
```

### Figure A Caption

The approved SDMx contract covers structure/codelists, access and disclosure rules,
snapshot/receipt semantics, residency and retention. Local synthetic development
needs no cloud credentials; sandbox access is optional and time-bounded. The
versioned package includes source, licenses, tests, runbooks, evidence and knowledge
transfer. No provider credentials or sandbox state accompany repository transfer.
Staging acceptance includes live persona, replay, recovery and disclosure tests.
Offboarding reviews groups, sessions/tokens, RBAC, vault, GitHub, ownership and
exports while retaining stable client runtime identities.

## Figure B Prompt: Client Production Information Flow

```text
Create a separate 16:9 enterprise information-flow diagram with the same white,
charcoal, restrained teal/blue palette as the engagement workflow. Prefer 3840x2160
where supported. Use large readable labels, flat shapes, clear arrowheads and ample
whitespace. No phase headers, approval diamonds, costs, cloud logos or provider lane.

TITLE: SovereignShield: Submission and Analyst Reconciliation
SUBTITLE: Latest submitted is distinct from current accepted publication

Place every main node inside one enclosure labelled "Client-controlled service".
The reporting authority is a separate box to its left. Draw only these nodes:
S1: Reporting authority / SDMx submission
S2: Approved SDMx file intake
S3: Protected archive and validation
S4: Governed submission history
S5: Current accepted publication
S6: Restricted submission / quarantine audit
S7: Analyst reconciliation / Expected filing versus receiver state
S8: Sender's expected filing evidence

All nodes except S1 and S8 are inside the client-controlled service. S8 belongs
beside S1 under the reporting authority, not inside a provider development area.

Allowed data arrows only:
S1 -> S2, labelled "SDMx files only"
S2 -> S3
S3 -> S4, labelled "Validated outcome and submission identity"
S4 -> S5, labelled "Current accepted selection"
S4 -> S6, labelled "Authorized audit selection"
S5 -> S7, labelled "Entitled current data"
S6 -> S7, labelled "Own-country submission feedback"
S8 -> S7, labelled "Expected ID, values and submission time"

S7 is a read/compare activity, not a producer or approver of S5 and S6. Never draw
arrows from S7 to either product. Do not call S6 the complete accepted history.
Show two product boxes side by side so publication and quarantine are distinct.
Use separate arrow routes into S7 to avoid overlapping labels or merged meanings.

Inside the client enclosure, place a short annotation beside S7:
"Compare IDs, submitted/received times, values and validation outcome."
Below S4, place:
"Rejected arrivals do not replace current accepted data."

Outside all data paths, add a small grey NOTE, with no arrows:
"Synthetic bank micro-transactions: educational calculation fixtures only;
not international submissions or production deliverables."
Do not draw a bank-transaction intake, a client-data cylinder in an external
provider area, or an arrow carrying confidential production records to a provider.

Separate amber review note, with no flow arrows:
"Disclosure review: public totals and row presence can reveal masked values.
Restrict or remove Researcher discovery where required."

FOOTER:
"Processing timestamps are not attested transport receipts.
Full accepted history requires an authorized history query."

Check that every publication/audit product originates at S4, and that S7 only
consumes evidence and entitled outputs. Do not print node IDs, rendering
instructions, "not shown", or this checklist in the finished image.
```

## Caption-Only Context

Keep these statements in document captions or surrounding prose instead of adding
small crowded panels to Figure A:

- **Portability:** technology-agnostic information/delivery pattern; Terraform
  provider/module adaptations for AWS, GCP, Microsoft Fabric or open-source stacks
  require equivalent controls and tests. Azure/Databricks is the implementation shown.
- **Evaluation:** approximately 75 minutes up including prerequisites, 30 minutes
  down and US$10 or less in Azure charges for the reference deploy/test/teardown
  cycle. These are observed synthetic-workload results, not SLAs or a price guarantee;
  see [measurement scope](RELEASE_EVIDENCE.md#reference-evaluation-metrics).
- **Disclosure:** observation existence is itself information. Removing researcher
  discovery does not repair reconstruction possible from public totals. Follow the
  [synthetic challenge and release criteria](../SECURITY.md#statistical-reconstruction-challenge).

## Editorial Acceptance Checks

- Every node occupies the specified phase and accountable-owner lane; headings do not repeat.
- There is one production approval gate and no staging-to-production bypass.
- Only an approved release reaches handover and client import; rework arrows are distinct.
- Confidential records and SDMx intake remain client-side; educational micro-data has no production path.
- Client operators accept handover, revoke provider access and verify runtime continuity in that order.
- Governed history supplies the products; the Analyst View consumes evidence and entitled results.
- Optional sandbox access and rework do not imply production-data feedback or standing credentials.
- Researcher discovery is conditional on disclosure approval; no reconstruction-proof masking claim appears.
- Inspect the downloaded image dimensions and text at the intended slide/PDF size.
  Pixel count alone does not establish readability.
- Review every arrow manually. Recreate persistent AI-rendering errors in an editable
  diagram source before publication; model-generated self-assurance is not evidence.