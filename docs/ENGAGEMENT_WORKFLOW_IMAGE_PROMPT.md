# Engagement Workflow Diagram Prompt

**Purpose:** a professional enterprise architecture diagram accompanying
[Nature of Engagement and Handover](ENTERPRISE_ONBOARDING_PLAYBOOK.md). The workflow
specification and renderable Mermaid remain authoritative if generated labels or
arrows differ. Verify every label and connection before publication.

## Image Generation Prompt

Create a precise enterprise consulting delivery and handover diagram titled
"SovereignShield: Nature of Engagement and Handover". Subtitle: "Synthetic-first
development; client-controlled production". Output a high-resolution 16:9 bitmap
(3840x2160 or larger), legible at presentation scale and suitable for an A3
landscape print. Use a white background, charcoal text, restrained teal for
provider development, blue for client-controlled environments, and amber for
approval gates. Use aligned rectangular process nodes, subtle 2-4px corners,
orthogonal connectors and ample whitespace. No gradients, 3D effects, decorative
shields, padlock wallpaper, mascots or stock imagery. Do not use institution or
vendor logos; names are plain text. Use consistent, readable sans-serif typography
with no dense paragraphs or text embedded in tiny icons.

Organize the diagram left-to-right into seven numbered phases across three
horizontal swimlanes. Label the lanes "Client Sponsor, Data Authority and Review",
"External Technical Provider", and "Client Platform and Operations". Show a
distinct dashed vertical trust boundary before client staging/production, and a
separate provider repository boundary enclosing only approved metadata, code and
synthetic fixtures. Avoid crossing arrows; route feedback along the bottom.

PHASE 1 - AGREE
Top lane node: "Scope, ownership, budget and acceptance".
Adjacent top node: "Approved SDMx contract, access matrix and disclosure policy".
Small inputs: "DSD / codelists", "snapshot and receipt semantics", "residency / retention".
Gate diamond: "Approved for synthetic development".
Only an arrow labeled "approved metadata; no production records" crosses into
the provider lane. Do not show bank micro-transactions as a client submission.

PHASE 2 - ESTABLISH
Provider node: "Approved independent or client repository" and "Local development; no cloud credentials".
Client platform node: "Client-owned sandbox, state backend and time-bounded access".
Show a dashed optional arrow labeled "approved synthetic sandbox access" to the
provider. Place "Production administration retained by client" beside the boundary.

PHASE 3 - BUILD AND TEST
Provider nodes: "Generate synthetic fixtures", then "Infrastructure, SDMx intake,
history and access controls", then "Credential-free tests and pull request".
Place a small secondary fixture node under generation: "Educational synthetic
micro-transactions: calculation example only". Connect it only to the fixture
generator, not to the international intake or production platform.

PHASE 4 - REVIEW
Top lane nodes: "Independent technical and security review" and "Disclosure challenge".
The disclosure node contains three short lines: "public-total reconstruction",
"row-existence inference", "restrict/remove Researcher if necessary".
Gate diamond: "Approved version and residual risks". A feedback arrow returns
to provider tests, labeled "review findings". The gate does not automatically
grant production access or trigger deployment.

PHASE 5 - HAND OVER
Across provider/client lanes: "Versioned source, licenses, tests, runbooks and knowledge transfer".
Client platform node: "Clone / fork / reviewed import into client repository".
Next node: "Client runtime identities, OIDC, vault, state and ownership".
Arrow note: "No provider credentials or sandbox state transferred".
Show one ownership transition: "client accepts repository and operational control".

PHASE 6 - ACCEPT AND DEPLOY
Client platform nodes: "Synthetic staging: live persona, replay and recovery tests",
then a top-lane gate "Production and disclosure approval", then "Client production deployment".
A protected cylinder labeled "Client confidential data" connects only to a
client-side "Approved SDMx file intake" node and the production platform.
No arrow from confidential data to the provider or public repository.
Label the platform "Azure + Databricks reference implementation".
A small side box says "Technology-agnostic pattern: AWS / GCP / Fabric / open source;
adapters and equivalent controls required". This is an option, not a deployed
multi-cloud topology or an automatically portable workload.

PHASE 7 - OPERATE AND EXIT
Client lane: "Operate, monitor, recover and review access".
Top lane: "Analyst reconciliation: expected latest filing vs receiver state".
Show two distinct outputs from governed history: "Current accepted publication"
and "Restricted submission / quarantine audit". Do not depict latest received
as automatically published.
Provider/client boundary node: "Offboard provider; verify continuity".
Below it list: "groups, sessions, RBAC, vault, GitHub, ownership".
Final node: "Client-owned runtime continues". Do not show deleting stable service
principals as routine personnel offboarding.

FOOTER AND LEGEND
Legend: solid arrow = approved artifact/data flow; dashed arrow = optional access
or feedback; diamond = client approval; dashed enclosure = trust/ownership boundary.
Small footer: "Independent synthetic reference architecture. No institutional or
vendor endorsement. Production acceptance remains client-owned."
Optional evaluation strip, separate from the production lane: "Reference synthetic
cycle: about 75 min up including prerequisites; 30 min down; Azure US$10 or less.
Observed evaluation, not an SLA or price guarantee." Do not imply these are
consulting fees, all-cloud benchmarks or production operating costs.

## Editorial Checks

- The provider never receives production data or standing production credentials.
- The international submission arrow contains SDMx files only; the educational
  micro-data artifact has no production intake arrow.
- Repository transfer, staging acceptance and production approval are separate.
- The Analyst View compares submitted evidence with actual receiver state.
- Researcher discovery is conditional on disclosure review; masking is not labeled
  reconstruction-proof.
- Terraform extensibility is not drawn as an already deployed multi-cloud system.
- Historical measurements are not represented as guaranteed cost or duration.
- Recreate any inaccurate AI-rendered text in a diagram editor before release.