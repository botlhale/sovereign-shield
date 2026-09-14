# SovereignShield Architecture Diagrams

> **Disclaimer.** An independent reference architecture, inspired by the design of
> public statistical portals such as the BIS Data Explorer. Not affiliated with or
> endorsed by the Bank for International Settlements or any central bank, and
> operating on **100% synthetic mock data**. BIS and SDMx appear as typeset text
> only, never as reproduced logos.

![Policy as a Metastore Object — promotion plane, ownership boundary between Terraform and the pipeline, data plane with quarantine isolation, and a consumption band, all resolving into a Unity Catalog policy enforcement point that maps five personas from public through auditor to "no group — zero rows, fails closed".](sovereign-shield_technical_vision.jpg)

*Rendered from [`technical_vision.md`](technical_vision.md). The Mermaid diagrams
below decompose the same system — use this one to orient an audience, and those
to answer the follow-up questions.*

These live-renderable Mermaid.js diagrams document how Azure Databricks and
Unity Catalog carry the security obligations of SDMx 3.0 statistical
submissions. GitHub, VS Code, Notion, Confluence, and most slide tooling render
them natively.

> All diagrams reflect the implemented system — object names, function names, and rule identifiers are taken from source, not illustrative.

> **On standards-body marks:** BIS and SDMx are referenced throughout as **typeset text**, never as reproduced logos, and dissemination targets are drawn generically. These visuals are intended for public posting; a rendered institutional logo beside this project's name would assert an affiliation that does not exist.

---

## Live-Renderable Diagrams

### 1.1 System Component Architecture

End-to-end topology from secret storage through governed consumption. Note that the **security layer is provisioned before any data is written**, and that both the raw ledger and the macro history carry row filters.

```mermaid
graph TD
    subgraph ORIGIN["🌍 SDMx 3.0 Submission Origin"]
        NCB["National Central Banks<br/><b>CA · US · GB</b><br/><i>structure-specific messages</i>"]
        RULEBOOK["BIS LBS Rulebook<br/><b>checks_lbs.xls</b><br/><i>LBS_CC01 to LBS_CC:21</i>"]
    end

    subgraph SEC["🔐 Secrets & Identity"]
        KV["Azure Key Vault<br/><i>spn-client-id · spn-client-secret<br/>spn-tenant-id · databricks-workspace-url</i>"]
        SPN["Service Principal<br/><b>spn-sovereignshield-cicd</b><br/><i>implicit owner of all assets</i>"]
    end

    subgraph ORCH["⚙️ Orchestration"]
        DAB["Databricks Asset Bundle<br/><b>sovereignshield_sdmx_pipeline</b>"]
        COMPUTE["Single-Node Job Compute<br/><b>DBR 18.x · Standard_DS3_v2</b><br/><i>num_workers 0 · SPOT_WITH_FALLBACK<br/>USER_ISOLATION</i>"]
    end

    subgraph TASKS["🔄 Pipeline Tasks"]
        T1["<b>1 · apply_security.py</b><br/><i>Triple-Lock DDL</i>"]
        T2["<b>2 · generate_sovereign_submissions.py</b><br/><i>SDMx 3.0 XML</i>"]
        T3["<b>3 · scd2_merge_engine.py</b><br/><i>aggregate · validate · merge</i>"]
        VAL["<b>sdmx_rule_validator.py</b><br/><i>BIS checks from checks_lbs.xls</i>"]
    end

    subgraph UC["🛡️ Unity Catalog — dbw_sovereignshield.sovereign_shield"]
        MICRO["<b>lbs_micro_transactions</b><br/>🔒 RLS fn_rls_micro_country_lock<br/><i>ON reporting_country</i>"]
        MACRO["<b>agg_sdmx_history</b><br/>🔒 RLS fn_rls_multi_persona_lock<br/><i>ON TIME_SERIES_CODE · BATCH_STATUS · OBS_CONF</i><br/>🎭 DDM fn_ddm_obs_conf_mask<br/><i>USING COLUMNS OBS_CONF, TIME_SERIES_CODE</i>"]
        VIEW["<b>v_agg_sdmx_published</b><br/><i>BATCH_STATUS = PUBLISHED<br/>AND IS_CURRENT = true</i>"]
    end

    subgraph GATEWAY["🌐 Public Dissemination Gateway"]
        API["<b>api_gateway.py</b><br/><i>chooses an identity,<br/>never chooses rows</i>"]
        UI["<b>portal_ui.py</b><br/><i>consumer tier</i>"]
        EXPORT["<b>sdmx_ml_exporter.py</b><br/><i>SDMX-ML 3.0 · JSON · CSV</i>"]
    end

    subgraph PERSONA["👥 Entra ID Personas — resolved at query time"]
        PUBLIC["<b>sg-...-public</b><br/><i>PUBLISHED + OBS_CONF = F</i>"]
        RESEARCH["<b>sg-...-researchers</b><br/><i>all PUBLISHED · values masked</i>"]
        SUBCA["<b>sg-...-submitter-ca</b><br/><i>CA in full · foreign public only</i>"]
        SUBUS["<b>sg-...-submitter-us</b><br/><i>US in full · foreign public only</i>"]
        ADMIN["<b>sg-...-admin</b><br/><i>1 = 1 · auditor</i>"]
        NONE["<b>no membership</b><br/><i>fails closed · zero rows</i>"]
    end

    KV -->|"dot-sourced pre_auth.ps1"| DAB
    KV -.->|"stores credentials for"| SPN
    SPN -->|"OAuth M2M · executes as owner"| DAB
    DAB --> COMPUTE
    COMPUTE --> T1
    NCB -.->|"jurisdictional submissions"| T2
    RULEBOOK -->|"parsed at runtime"| VAL
    T1 -->|"RLS · DDM · View · DDL"| UC
    T1 --> T2
    T2 -->|"submission batch"| T3
    T3 <-->|"validate batch"| VAL
    T3 -->|"append ledger"| MICRO
    T3 -->|"SCD2 MERGE"| MACRO
    MICRO -.->|"micro to macro rollup"| MACRO
    MACRO --> VIEW

    UI --> API
    API --> EXPORT
    API -->|"caller token, or public proxy SPN"| MACRO

    MACRO --> ADMIN
    MICRO --> ADMIN
    MACRO --> SUBCA
    MACRO --> SUBUS
    MICRO --> SUBCA
    MICRO --> SUBUS
    MACRO --> RESEARCH
    MACRO --> PUBLIC
    MACRO -.->|"FALSE"| NONE

    classDef secret fill:#1a1a2e,stroke:#f39c12,stroke-width:2px,color:#fff
    classDef orch fill:#16213e,stroke:#3498db,stroke-width:2px,color:#fff
    classDef task fill:#0f3460,stroke:#00d9ff,stroke-width:2px,color:#fff
    classDef data fill:#1b3a2f,stroke:#2ecc71,stroke-width:2px,color:#fff
    classDef people fill:#2c1a3e,stroke:#c39bd3,stroke-width:2px,color:#fff
    classDef origin fill:#132c3d,stroke:#5dade2,stroke-width:2px,color:#fff
    classDef edge fill:#3d1a2c,stroke:#e59866,stroke-width:2px,color:#fff

    class NCB,RULEBOOK origin
    class KV,SPN secret
    class DAB,COMPUTE orch
    class T1,T2,T3,VAL task
    class MICRO,MACRO,VIEW data
    class ADMIN,SUBCA,SUBUS,RESEARCH,PUBLIC,NONE people
    class API,UI,EXPORT edge
```

**Reading the diagram**

| Element | Significance |
| --- | --- |
| `NCB → T2` | Submissions originate per jurisdiction — sovereignty is a property of the input, not a later annotation |
| `RULEBOOK → VAL` | The BIS rulebook is read at runtime; a standards revision needs no redeployment |
| `KV → DAB` | Credentials are hydrated into session scope at deploy time; no literal is ever stored |
| `T1` runs first | No table exists un-governed, even momentarily |
| Filters on **both** tables | Protecting only the aggregate would leave the raw ledger exposed |
| `API → MACRO`, not `API → VIEW` | A Unity Catalog view resolves group membership against the **view owner**, so per-caller entitlement has to be evaluated against the base table |
| `MACRO → NONE` dashed | The fail-closed default. Off-boarding and inter-sovereign isolation are the same code path |

**The Zero-Trust identity boundary**

Every arrow from `MACRO` to a persona is the *same* query against the *same*
table. Nothing in the gateway, the portal or the exporter narrows it. The
difference in what each persona receives is produced entirely inside the
metastore, which is why the boundary holds across PySpark, a SQL warehouse, a BI
tool and the public REST API without being re-implemented for any of them.

---

### 1.1a Ownership boundary — who writes which object

Two declarative systems, disjoint by design. Terraform reports drift on anything
it owns; the bundle re-applies its own objects on every run. An object written
by both would oscillate, and a Terraform apply could detach a live row filter
mid-query.

```mermaid
flowchart LR
    subgraph TF["🏗️ Terraform — infrastructure & access control"]
        direction TB
        TF1["Entra groups · service principals<br/>OIDC federation · Key Vault"]
        TF2["Workspace · access connector<br/>storage credential · external location"]
        TF3["Catalog · schema · SQL warehouse"]
        TF4["GRANT USE CATALOG / USE SCHEMA / SELECT<br/><i>additive databricks_grant</i>"]
    end

    subgraph DABS["📦 Asset Bundles — data & policy"]
        direction TB
        DB1["Table DDL"]
        DB2["Policy UDFs<br/>fn_rls_multi_persona_lock<br/>fn_ddm_obs_conf_mask"]
        DB3["SET ROW FILTER · SET MASK<br/><i>detach → replace → re-attach</i>"]
        DB4["v_agg_sdmx_published"]
    end

    TF3 -->|"namespace exists before tables"| DB1
    TF4 -.->|"reachability"| DB3
    DB3 -.->|"visibility"| DB3

    classDef tf fill:#2c1a3e,stroke:#c39bd3,stroke-width:2px,color:#fff
    classDef db fill:#0f3460,stroke:#00d9ff,stroke-width:2px,color:#fff
    class TF1,TF2,TF3,TF4 tf
    class DB1,DB2,DB3,DB4 db
```

> **The grant decides reachability; the row filter decides visibility.** Trying
> to express sovereignty through grants instead would need one securable per
> jurisdiction and still could not mask a single cell.

---

### 1.2 Data Ingestion & Atomic Quarantine Sequence

The defining behaviour of the platform: a failed revision is **fully recorded for audit yet cannot degrade what consumers already see**. The prior published record stays active.

```mermaid
sequenceDiagram
    autonumber
    participant SUB as 🏦 Reporting Agent
    participant GEN as generate_sovereign_submissions.py
    participant ENG as scd2_merge_engine.py
    participant VAL as sdmx_rule_validator.py
    participant XLS as checks_lbs.xls
    participant HIST as agg_sdmx_history
    participant VIEW as v_agg_sdmx_published
    participant RES as 🔬 Researcher

    Note over SUB,VIEW: CYCLE 1 — BASELINE (clean submission)

    SUB->>GEN: Submit CA micro-transactions for 2026-Q1
    GEN->>ENG: SDMx 3.0 batch
    ENG->>ENG: Normalize codes, roll up to 11-dimension key
    ENG->>VAL: Aggregated macro batch
    VAL->>XLS: Parse BIS consistency checks at runtime
    XLS-->>VAL: LBS_CC01 to LBS_CC:21
    VAL-->>ENG: PASS — BATCH_STATUS = PUBLISHED
    ENG->>HIST: Insert 9 rows, IS_CURRENT = true, VALID_TO = 9999-12-31
    RES->>VIEW: SELECT
    VIEW-->>RES: ✅ CA baseline visible

    Note over SUB,VIEW: CYCLE 2 — REVISION (all jurisdictions fail independently)

    SUB->>GEN: Resubmit CA 2026-Q1 with revised figures
    GEN->>ENG: SDMx 3.0 batch
    ENG->>VAL: Aggregated macro batch
    VAL->>VAL: Evaluate aggregate vs components, tolerance 1e-4

    rect rgb(60, 20, 20)
        Note over VAL: CA · LBS_CC01<br/>US · LBS_CC01<br/>GB · LBS_CC02, LBS_CC:04
        VAL->>VAL: Group by (L_REP_CTY, DATE) and apply verdict atomically
        VAL-->>ENG: FAIL — 22 revision rows QUARANTINE<br/>4 offending observations attributed
    end

    ENG->>ENG: Split incoming batch on BATCH_STATUS

    rect rgb(20, 45, 30)
        Note over ENG,HIST: Prior-state preservation
        ENG--xHIST: Stage 1 expire — SKIPPED for quarantined rows
        ENG->>HIST: Stage 2b append audit rows<br/>IS_CURRENT = false, VALID_TO = VALID_FROM
        ENG--xHIST: Stage 3 logical delete — quarantined keys excluded
        Note over HIST: ✅ Baseline rows remain IS_CURRENT = true
    end

    RES->>VIEW: SELECT
    VIEW-->>RES: ✅ Still serving the last valid baseline

    Note over SUB,VIEW: Failure degrades to stale data, never to missing data

    SUB->>HIST: Query own jurisdiction (RLS scoped to CA)
    HIST-->>SUB: 🔍 QUARANTINE rows with FAILED_RULE_ID for diagnosis
```

**Guarantees demonstrated**

| Guarantee | Mechanism |
| --- | --- |
| All-or-nothing acceptance | Verdict grouped by `(L_REP_CTY, DATE)` — one failure quarantines the whole country-quarter |
| Blast-radius containment | US and GB batches in the same run publish normally |
| Continuity of service | Quarantined rows bypass the expire-merge, so the baseline stays `IS_CURRENT = true` |
| Auditability | Rejection persisted with `FAILED_RULE_ID`, visible to the owning submitter |
| Replay safety | `left_anti` join on key + `version_hash` blocks duplicate audit rows |

---

### 1.3 Optional — Triple-Lock Enforcement Path

A compact supporting visual for security-focused slides.

```mermaid
graph LR
    Q["📥 Incoming Query"] --> L1

    subgraph LOCKS["🛡️ Triple Lock"]
        L1["<b>Lock 1 — RLS</b><br/>fn_rls_multi_persona_lock<br/><i>row granularity</i>"]
        L2["<b>Lock 2 — DDM</b><br/>fn_ddm_obs_conf_mask<br/><i>cell granularity</i>"]
        L3["<b>Lock 3 — Quarantine View</b><br/>v_agg_sdmx_published<br/><i>result-set granularity</i>"]
    end

    L1 -->|"segment 9 matches<br/>Entra ID group"| L2
    L1 -.->|"no match — row removed"| DROP["🚫 Row Withheld"]
    L2 -->|"OBS_CONF = F"| L3
    L2 -.->|"OBS_CONF = C or N"| MASK["🎭 OBS_VALUE → NULL"]
    L3 -->|"PUBLISHED and IS_CURRENT"| OUT["✅ Governed Result"]
    L3 -.->|"QUARANTINE or superseded"| HIDE["🚫 Row Withheld"]
    MASK --> L3

    classDef lock fill:#0f3460,stroke:#00d9ff,stroke-width:2px,color:#fff
    classDef deny fill:#3a1520,stroke:#e74c3c,stroke-width:2px,color:#fff
    classDef allow fill:#1b3a2f,stroke:#2ecc71,stroke-width:2px,color:#fff

    class L1,L2,L3 lock
    class DROP,HIDE,MASK deny
    class OUT allow
```

---

### 1.4 Safe Engagement — Build on Synthetic, Hand Over, Revoke

How an external specialist builds and proves the platform **without ever holding real data**, and how the institution severs that access in three administrative actions without modifying the delivered code.

```mermaid
graph LR
    subgraph BUILD["🧪 Phase 1 — Build (external specialist)"]
        SYN["Synthetic submissions<br/><i>generate_sovereign_submissions.py</i>"]
        RULES["Public BIS rulebook<br/><i>checks_lbs.xls</i>"]
        DDL["Declarative security<br/><i>unity_catalog_triple_lock.sql</i>"]
        BUNDLE["Deployment manifest<br/><i>databricks.yml</i>"]
    end

    subgraph HANDOVER["📦 Phase 2 — Handover"]
        REPO["Git repository<br/><b>zero credentials inside</b>"]
    end

    subgraph PROD["🏛️ Phase 3 — Enterprise runs it on real data"]
        OWNSPN["Enterprise service principal"]
        OWNCAT["Enterprise Unity Catalog"]
        REAL["Real submissions"]
    end

    subgraph REVOKE["🔒 Phase 4 — Cut-off (no code change)"]
        R1["1 · Rotate SPN<br/><i>kv_spn_remediation.sh</i>"]
        R2["2 · Drop Key Vault access policy"]
        R3["3 · Remove from Entra ID groups"]
    end

    SYN --> DDL
    RULES --> DDL
    DDL --> BUNDLE
    BUNDLE --> REPO
    REPO --> OWNSPN
    OWNSPN --> OWNCAT
    REAL --> OWNCAT
    OWNCAT --> R1
    R1 --> R2
    R2 --> R3
    R3 --> ZERO["🚫 Builder resolves to<br/><b>zero groups → zero rows</b><br/><i>same path that enforces sovereignty</i>"]

    classDef build fill:#132c3d,stroke:#5dade2,stroke-width:2px,color:#fff
    classDef hand fill:#16213e,stroke:#3498db,stroke-width:2px,color:#fff
    classDef prod fill:#1b3a2f,stroke:#2ecc71,stroke-width:2px,color:#fff
    classDef rev fill:#3a1520,stroke:#e74c3c,stroke-width:2px,color:#fff

    class SYN,RULES,DDL,BUNDLE build
    class REPO hand
    class OWNSPN,OWNCAT,REAL prod
    class R1,R2,R3,ZERO rev
```

**Why this holds**

| Property | Why it survives the handover |
| --- | --- |
| No real data in the build | Submissions are generated; the public rulebook supplies the checks. Nothing is calibrated against live distributions |
| No credentials in the deliverable | `pre_auth.ps1` resolves secrets by *name* at run time, so the repository never contains a value to leak |
| No re-implementation risk | Controls are Unity Catalog objects, so they activate on real data on the first run — there is no "productionisation" pass that could get the security wrong |
| No bespoke off-boarding path | Row filters grant on positive group membership and fail closed. Zero groups yields zero rows, using the same code path that separates jurisdictions |

## Export Guidance

| Target | Approach |
| --- | --- |
| **GitHub / Confluence / Notion** | Paste the Mermaid blocks directly — rendered natively |
| **PowerPoint / Google Slides** | Render at [mermaid.live](https://mermaid.live), export SVG, then insert (SVG stays crisp when scaled) |
| **PDF / print** | Export SVG rather than PNG; the `classDef` colours are tuned for dark backgrounds, so invert for light-theme print |
| **VS Code preview** | Built-in Markdown preview renders Mermaid without an extension |

> When editing the diagrams, keep object and function names synchronized with `src/unity_catalog_triple_lock.sql` and `src/scd2_merge_engine.py`. These visuals are cited in executive material, so drift between the diagram and the deployed system is a correctness problem, not a cosmetic one.
