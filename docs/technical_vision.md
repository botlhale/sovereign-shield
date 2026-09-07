# Technical Vision — Data Model & Dissemination Specification

**Audience:** architects, security advisors, platform engineers, technical review boards
**Companion:** [`executive_vision.md`](executive_vision.md) for the SLT case ·
[`technical_reference.md`](technical_reference.md) for implementation detail ·
[`image_prompts.md`](image_prompts.md) to regenerate the diagram

![Policy as a Metastore Object — four bands: a promotion plane from pull request to OIDC token; an ownership boundary splitting Terraform from the pipeline across a divider reading "one writer per object"; a data plane routing passes to a history table and failures to audit-only quarantine; and a consumption band whose gateway "chooses an identity, never chooses rows". All resolve into a Unity Catalog enforcement point listing five personas.](sovereign-shield_technical_vision.jpg)

---

## Design intent

The architecture carries two ownership boundaries and one enforcement point, and
all three are explicit rather than hidden behind a generic "governance" layer.
An architect will ask where policy is evaluated and what stops the pipeline and
Terraform fighting; both answers are structural, not procedural.

---

## The series key

Every entitlement decision reads the same artefact: an 11-segment dot-separated
SDMx key.

```text
FREQ . L_MEASURE . L_POSITION . L_INSTR . L_DENOM . L_CURR_TYPE
     . L_PARENT_CTY . L_REP_BANK_TYPE . L_REP_CTY . L_CP_SECTOR . L_CP_COUNTRY
  ▲                                          ▲
segment 1                                segment 9
cadence                            reporting jurisdiction
```

| Segment | Dimension | Role |
| --- | --- | --- |
| 1 | `FREQ` | Reporting cadence. Partitions the catalogue |
| 2 | `L_MEASURE` | Measure type |
| 3 | `L_POSITION` | Claims or liabilities |
| 4 | `L_INSTR` | Instrument |
| 5 | `L_DENOM` | Currency denomination |
| 6 | `L_CURR_TYPE` | Domestic / foreign / unallocated |
| 7 | `L_PARENT_CTY` | Parent country |
| 8 | `L_REP_BANK_TYPE` | Reporting bank type |
| **9** | **`L_REP_CTY`** | **Reporting jurisdiction — the sovereignty anchor** |
| 10 | `L_CP_SECTOR` | Counterparty sector |
| 11 | `L_CP_COUNTRY` | Counterparty country |

Segment 9 is read by **both** the row filter and the column mask. The filter
decides whether a row is visible; the mask independently re-checks the same
segment before revealing a value, so a caller who reaches a foreign confidential
row through an additive entitlement still cannot read it.

Segment lookup uses `try_element_at` wrapped in a `coalesce` to `FALSE`. A row
filter is evaluated on every row of every query, so a malformed key that raised
would abort *all* access to the table — a data-quality defect escalating into a
total outage. Instead the malformed row becomes invisible.

## The history table

`agg_sdmx_history` holds the aggregate layer. It is named for the aggregation
grain rather than a collection, because the engine is domain-agnostic.

| Column | Purpose |
| --- | --- |
| `TIME_SERIES_CODE` | The 11-segment key above |
| `DATE` | Reporting period, shaped per cadence |
| `AGG_CODE` | Framework code (`LBSR` for the BIS LBS example) |
| `OBS_VALUE` | The observation. Signed — negative is legitimate, not a failure. Carries the column mask |
| `OBS_STATUS` | SDMx observation status |
| `OBS_CONF` | `F` free to publish, `C` confidential, `N` not for publication |
| `QUALITY_STATUS` | `PASS` / `FAIL`, assigned atomically per batch |
| `FAILED_RULE_ID` | Sorted union of violated check codes |
| `BATCH_STATUS` | `PUBLISHED` / `QUARANTINE` |
| `version_hash` | Payload fingerprint driving SCD2 change detection |
| `VALID_FROM` / `VALID_TO` / `IS_CURRENT` | SCD2 interval |

Natural key for the merge: `(TIME_SERIES_CODE, DATE, AGG_CODE)`.

Zero-valued observations are not stored. Under SDMx convention a position that
nets to zero is simply not reported, and a masked value is serialised as
**absent** rather than as zero — conflating the two would turn a confidentiality
control into a data-quality defect.

---

## Multi-frequency ingestion

Locational Banking Statistics is collected quarterly. **The platform is not a
quarterly platform.** A statistical hub receives collections on several cadences
into the same history table, and `FREQ` is segment 1 precisely so they can
coexist without separate tables.

| Cadence | `FREQ` | Period label | Periods per year |
| --- | --- | --- | --- |
| Annual | `A` | `2026` | 1 |
| Semi-annual | `S` | `2026-S1` | 2 |
| Quarterly | `Q` | `2026-Q1` | 4 |
| Monthly | `M` | `2026-03` | 12 |

Three consequences follow:

* **Period labels are cadence-shaped.** A monthly series labelled `2026-Q1` would
  sort and group correctly by accident while being wrong.
  `generate_stress_test_data.py` builds each cadence's labels in its own form.
* **Ingestion takes `freq` as a batch parameter.** `process_and_publish_macro_batch`
  and `run_pipeline` accept it; nothing is hardcoded to `Q`.
* **Quarantine is atomic per jurisdiction *and period*.** A monthly break in one
  country does not quarantine that country's annual submission.

---

## Dissemination Gateway API

The gateway decides *which identity* a query runs as. Unity Catalog decides *what
that identity may see*. No persona branch exists anywhere in the serving code.

### Identity resolution

| Caller | Runs as | Carrier |
| --- | --- | --- |
| Signed-in workspace user | Their own token | `X-Forwarded-Access-Token` |
| Container Apps visitor | Their own token | `X-MS-TOKEN-AAD-ACCESS-TOKEN` |
| Direct API client | Their own token | `Authorization: Bearer` |
| Anonymous visitor | `spn-sovereignshield-public` | The app's own service principal |

Tokens are validated against the workspace SCIM `me` endpoint rather than by
hand-rolled JWT verification, and only a SHA-256 digest is cached.

### Endpoints

| Route | Returns |
| --- | --- |
| `GET /api/v1/search` | Filtered observations |
| `GET /api/v1/facets` | Distinct codes per filter, already persona-scoped |
| `GET /api/v1/export/sdmx-ml` | SDMX-ML 3.0 structure-specific message |
| `GET /api/v1/export/sdmx-json` | SDMX-JSON 2.0.0 |
| `GET /api/v1/export/csv` | SDMX-CSV 2.0.0, or `?format=tidy` |
| `GET /api/v1/whoami` | Resolved security context |
| `GET /api/v1/health` | Catalog connectivity, backend mode, structure availability |

### Filter parameters

| Parameter | Dimension | Example |
| --- | --- | --- |
| `frequency` | `FREQ` | `A`, `S`, `Q`, `M` |
| `parent_country` | `L_PARENT_CTY` | `CA`, `5J` |
| `reporting_country` | `L_REP_CTY` | `CA`, `US` |
| `counterpart_sector` | `L_CP_SECTOR` | `B`, `N`, `A` |
| `counterpart_country` | `L_CP_COUNTRY` | `US`, `5J` |
| `currency` | `L_DENOM` | `CAD`, `USD`, `TO1` |
| `position` | `L_POSITION` | `C`, `L` |
| `instrument` | `L_INSTR` | `A`, `B`, `G` |
| `date_from` / `date_to` | `DATE` | Inclusive period bounds |
| `include_quarantined` | `BATCH_STATUS` | Own batches only; the filter still applies |

`frequency` is presented first in the portal because it partitions the
catalogue: comparing a monthly series against a quarterly aggregate of the same
position is a category error, and the filter is the cheapest place to prevent it.

Values are bound as query parameters and additionally constrained to
`[A-Za-z0-9_]{1,12}`. Binding already prevents injection; the pattern check keeps
malformed input from being blamed on the metastore.

**Facets are persona-scoped.** A visitor cannot discover that a code exists if the
row filter hides every row carrying it — otherwise the facet list would leak the
shape of data the caller cannot read.

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
| "Synthetic data proves nothing about scale." | Volumetrics, skew and cost at real volume need a production dry-run. The scale harness demonstrates that entitlement enforcement stays vectorised and roughly linear to 100k+ rows; it does not model concurrent production load. |
