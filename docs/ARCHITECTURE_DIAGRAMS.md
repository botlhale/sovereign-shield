# SovereignShield Architecture Diagrams

These Mermaid diagrams specify the current reference data flow and its ownership
boundaries. Technology and institution names are plain text, not endorsements.
The deployment uses synthetic observations and logical jurisdictional segregation.
For implementation details see [the technical reference](technical_reference.md).

The [publication figure sources](figures/README.md) provide matching SVG/PNG
schematics and a source/image integrity manifest for the Executive Brief and
White Paper. Portal screenshots have a separate [capture inventory](../demo/README.md).

## Live-Renderable Diagrams

### 1.1 System Component Architecture

The international intake contract is **SDMx files only**. Synthetic bank
micro-transactions are educational artifacts showing the calculation of realistic
observations; the separate demo ledger is not a client intake requirement or
system deliverable. It has no production micro-to-macro ingestion arrow.

```mermaid
flowchart TB
    subgraph DEMO["Synthetic fixture preparation: education only"]
        MICROFIX["Generated bank micro-transactions"] --> GENERATOR["Aggregate and classify fixture observations"]
        GENERATOR --> XML["Synthetic SDMx files"]
        MICROFIX -.-> LEDGER["Protected demo ledger: sovereign_intake"]
    end
    subgraph INTAKE["Modeled international intake"]
        SUB["Reporting authority"] -->|SDMx files only| ARCHIVE["Admin-only submission archive"]
        XML --> ARCHIVE
        ARCHIVE --> VALIDATE["Pinned structure and implemented workbook checks"]
        VALIDATE --> HISTORY["Submission-aware history: one Delta MERGE"]
        STRUCTURE["Reviewed DSD, codelists and rulebook"] --> VALIDATE
    end
    subgraph GOVERNANCE["Unity Catalog: supported query paths"]
        HISTORY --> POLICIES["Account-group RLS and decimal value mask"]
        GROUPS["Databricks account memberships"] --> POLICIES
        ENTRA["Entra identities"] -.->|setup reconciliation| GROUPS
    end
    subgraph SERVE["Trusted serving plane"]
        DBAPP["Databricks App: SSO"] --> GATEWAY["Identity, user filters and lifecycle selection"]
        ACA["Container Apps: anonymous or Easy Auth"] --> GATEWAY
        GATEWAY -->|caller or explicit public principal| POLICIES
        POLICIES --> RESULT["Entitled result"]
        RESULT --> PUBLISHED["Current published SDMx products"]
        RESULT --> AUDIT["Authorized submission/audit product"]
    end
    PUBLISHED --> PUBLIC["Public: published free values"]
    PUBLISHED --> RESEARCHER["Researcher: disclosure-approved discovery"]
    AUDIT --> ANALYST["Analyst: reconcile expected filing with receiver state"]
    AUDIT --> ADMIN["Administrator: authorized history and oversight"]
```

The gateway handles tokens and results and therefore remains trusted. UC policies
enforce row/value entitlements independently of the gateway's filter predicates.
Published feeds select current accepted data; the underlying row filter does not
itself enforce `IS_CURRENT`. Raw storage and privileged control-plane access need
separate protection.

### 1.1a Ownership Boundary

```mermaid
flowchart LR
    subgraph TF["Terraform: infrastructure and grants"]
        ID["Entra apps/groups, federation and vault"]
        INFRA["Workspace, storage, namespaces and compute policy"]
        GRANTS["One writer per principal/securable grant pair"]
    end
    subgraph ACCOUNT["Account setup and run-as permission"]
        MEMBERS["Databricks account memberships and assignments"]
        RUNAS["Exact runtime service-principal use grant"]
    end
    subgraph BUNDLE["Bundle and policy executor: data and policy"]
        JOB["Stable run_as and ordered pipeline tasks"]
        FUNCTIONS["Immutable content-addressed policy functions"]
        TABLES["Protected table DDL and verified bindings"]
        APP["Uploaded App source and exact-deployment activation"]
    end
    ID --> MEMBERS --> RUNAS --> JOB
    INFRA --> TABLES
    FUNCTIONS -->|bind without detaching existing protection| TABLES
    GRANTS -->|approved access after objects exist| TABLES
    JOB --> FUNCTIONS
    JOB --> APP
```

Normal policy deployment never detaches row filters or masks. Changing a grant
pair through multiple owners is prohibited. Stable runtime identities do not
automatically migrate object ownership or remove human administration rights.

### 1.2 Data Ingestion and Atomic Quarantine Sequence

```mermaid
sequenceDiagram
    autonumber
    participant AUTH as Reporting authority or synthetic generator
    participant ARCH as Protected SDMx archive
    participant VAL as Contract and arithmetic validator
    participant HIST as Submission-aware Delta history
    participant PUB as Current published product
    participant ANALYST as Own-jurisdiction analyst
    AUTH->>ARCH: Full country/period/aggregation SDMx snapshot and immutable ID
    ARCH->>VAL: Submitted observations, source digest and message metadata
    VAL-->>HIST: PASS / PUBLISHED with coverage notes
    HIST->>HIST: One MERGE: close exact current scope and insert snapshot
    Note over HIST: Current VALID_TO is NULL; genuine zero is retained
    HIST-->>PUB: Accepted current observations, subject to entitlements
    AUTH->>ARCH: Later filing with a named arithmetic failure
    ARCH->>VAL: New immutable submission
    VAL-->>HIST: FAIL / QUARANTINE and observation/batch feedback
    HIST->>HIST: One MERGE: insert audit-only rows, leave accepted state unchanged
    HIST-->>PUB: Prior accepted publication remains current
    ANALYST->>HIST: Authorized published / all / quarantine query
    HIST-->>ANALYST: IDs, timestamps, actual values and validation outcomes
    Note over ANALYST: Reconcile expected latest filing with receiver state
    ARCH->>HIST: Replay same ID and content
    HIST-->>ARCH: No duplicate rows or new history commit
```

An accepted smaller replacement retires omitted keys in its own scope. A new
identical filing is retained as a distinct submission; replay of the same message
is not. Older accepted arrivals are audit-only. The synthetic baseline contains
22 published observations and its revision 22 quarantined observations across
CA, US and GB. The ledger and macro history are separate transactions.

### 1.3 Entitlement and Information Disclosure

```mermaid
flowchart LR
    REQUEST["Authenticated SQL principal"] --> RLS["Account-group row entitlement"]
    RLS --> MASK["Admin or own country: reveal; otherwise explicit F only"]
    MASK --> SELECT["Current published product or authorized audit selection"]
    SELECT --> RELEASE["Entitled output"]
    RELEASE -.-> RISK["Totals, row existence and revisions can reveal masked values"]
    RISK --> REVIEW["Disclosure assessment and synthetic challenge"]
    REVIEW --> GATE{"Approved release product?"}
    GATE -->|No| RESTRICT["Suppress or redesign release; restrict/remove Researcher if necessary"]
    GATE -->|Yes| APPROVE["Client data authority records release approval"]
```

This is a conceptual control map, not a physical SQL execution order or an
implemented disclosure-control engine. RLS/DDM does not stop statistical inference.
Community tests of the [open challenge](../SECURITY.md#statistical-reconstruction-challenge)
must use synthetic data. Removing researcher discovery alone does not repair
reconstruction possible from public totals.

### 1.4 Safe Engagement: Build, Hand Over, Approve and Revoke

```mermaid
flowchart LR
    SCOPE["Client: scope, metadata and acceptance"] --> BUILD["Provider: approved repository and synthetic development"]
    BUILD --> REVIEW["Independent client review"]
    REVIEW --> TRANSFER["Versioned source, tests, licenses and runbooks"]
    TRANSFER --> IMPORT["Client clone/fork/import and identity configuration"]
    IMPORT --> STAGE["Synthetic staging and live acceptance"]
    STAGE --> GATE{"Client production approval"}
    GATE -->|Approved| PROD["Client production SDMx intake"]
    GATE -->|Revise| BUILD
    REAL["Client confidential data: remains client-side"] --> PROD
    PROD --> OPERATE["Client operators and analyst reconciliation"]
    OPERATE --> REVOKE["Revoke provider access; retain runtime identities"]
```

No production records, provider credentials or sandbox state cross with the
repository transfer. The client accepts production adaptations, disclosure,
residency, recovery and operating cost. Offboarding covers groups, sessions,
tokens, RBAC, vault, GitHub, ownership and retained exports. See the
[engagement specification](ENTERPRISE_ONBOARDING_PLAYBOOK.md) and the detailed
[image prompt](ENGAGEMENT_WORKFLOW_IMAGE_PROMPT.md).

## Evaluation and Extensibility

Successful reference provisioning and teardown measured approximately **75 minutes
up including prerequisites**, **30 minutes down**, and **US$10 or less in Azure
charges for deploy/test/teardown**. See [measurement scope](RELEASE_EVIDENCE.md#reference-evaluation-metrics).
These diagrams are not production performance or pricing guarantees.

The pattern is technology-agnostic. Terraform enables provider/module extensions
to AWS, GCP, Microsoft Fabric and open-source stacks; equivalent identity, policy,
storage and lifecycle adapters must be implemented and verified. These diagrams
show the Azure/Databricks implementation, not an already deployed multi-cloud estate.

## Export Guidance

Render Mermaid in GitHub or a compatible extension/tool. Support in VS Code,
Confluence, Notion and slide software depends on the renderer or plugin; it is
not universally built in. For slides/print, export a reviewed diagram as SVG or
high-resolution PNG and verify text, arrows and color contrast. Use the current
Mermaid specifications to replace older conceptual artwork when its embedded
labels conflict with this contract.