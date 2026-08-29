# Minimal Viable Synthetic Dataset (MVSD) — BIS LBS Specification

> **Purpose.** This is the data contract a hiring organisation hands to an external
> contractor so that the contractor can build, test and demonstrate the entire
> platform **without ever touching a production record**. It specifies structure,
> codelists and required test coverage — never values.
>
> **Authority.** Structure is derived from the live BIS registry
> (`https://stats.bis.org/api/v1/datastructure/BIS/BIS_LBS/latest?references=all`)
> and reconciled against `docs/reference_standards/checks_lbs.xls`,
> `src/generate_sovereign_submissions.py` and `src/sdmx_rule_validator.py`.

---

## 1. Structure identity

| Artefact | Identifier |
| --- | --- |
| Data Structure Definition | `BIS:BIS_LBS(1.0)` |
| Dataflow (dissemination) | `BIS:WS_LBS_D_PUB(1.0)` |
| Message format | SDMX-ML 3.0 `StructureSpecificData` |
| Dimension at observation | `TIME_PERIOD` |
| Aggregation framework | `LBSR` (Locational Banking Statistics, restated basis) |

SDMX 3.0.0 **removed** the Generic Data format. `StructureSpecificData` is the only
XML data message the standard still defines; anything emitting `GenericData` is
producing a 2.1-era payload.

---

## 2. Dimension set (authoritative)

The composite `TIME_SERIES_CODE` is **eleven** dot-separated segments in exactly
this order. Segment order is not cosmetic: position 9 is the sovereignty anchor
that the Unity Catalog row filter reads.

| # | Dimension | Meaning | Codes used by the MVSD |
| --- | --- | --- | --- |
| 1 | `FREQ` | Frequency | `Q` |
| 2 | `L_MEASURE` | Measure | `S` (amounts outstanding) |
| 3 | `L_POSITION` | Balance-sheet position | `C` claims, `L` liabilities |
| 4 | `L_INSTR` | Instrument | `A` all, `B`, `D` deposits/loans, `G` |
| 5 | `L_DENOM` | Currency denomination | `CAD`, `USD`, `GBP`, `EUR`, `JPY`, `CHF`, `TO1` (all currencies), `UN9` (unallocated) |
| 6 | `L_CURR_TYPE` | Currency type | `D` domestic, `F` foreign, `A` all, `U` unallocated |
| 7 | `L_PARENT_CTY` | Parent country | `5J` (all countries) |
| 8 | `L_REP_BANK_TYPE` | Reporting bank type | `A` (all types) |
| 9 | **`L_REP_CTY`** | **Reporting country — RLS anchor** | `CA`, `US`, `GB` |
| 10 | `L_CP_SECTOR` | Counterparty sector | `A` all, `B` banks, `N` non-banks, `M`, `F`, `C`, `G`, `H` |
| 11 | `L_CP_COUNTRY` | Counterparty country | `5J`, `DE`, `FR`, `JP`, `GB`, `CA`, `US` |

Plus the time dimension, measure and observation-level attributes:

| Component | Role | Values |
| --- | --- | --- |
| `TIME_PERIOD` | Time dimension | `2026-Q1` (ISO 8601 quarterly) |
| `OBS_VALUE` | Measure | Signed `DOUBLE`, millions |
| `OBS_STATUS` | Attribute | `A` normal, `B` break in series |
| `OBS_CONF` | Attribute | `F` free to publish, `C` confidential, `N` not for publication |

### 2.1 Reconciliation with earlier drafts

An earlier specification circulated with dimension names that do **not** exist in
the BIS_LBS structure or anywhere in this repository. They are recorded here so
the discrepancy is documented rather than silently corrected, and so nobody
reintroduces them:

| Draft name | Occurrences in repo | Authoritative name |
| --- | --- | --- |
| `L_POS_TYPE` | 0 | `L_POSITION` |
| `L_TYPE` | 0 | `L_INSTR` |
| `L_CP_CTY` | 0 | `L_CP_COUNTRY` |
| `CURR_TYPE` | 0 | `L_CURR_TYPE` |
| `CONF_STATUS` | 0 | `OBS_CONF` |
| `REP_CTY` | derived column only | `L_REP_CTY` |
| *(omitted from draft)* | — | `L_DENOM`, `L_PARENT_CTY` |

The draft omitted two dimensions entirely, which makes an eleven-segment key
unconstructible. Adopting the draft names would additionally break the
`try_element_at(split(TIME_SERIES_CODE, '\\.'), 9)` sovereignty anchor, the
`checks_lbs.xls` rule matching, and every submission XML already emitted.

`UNIT_MULT` and `DECIMALS` are legitimate BIS_LBS dataset-level attributes but are
not currently carried by the MVSD; they are constant across the synthetic
corpus and add no test coverage. Add them only if a downstream consumer needs
them for scaling.

---

## 3. Codelist semantics that change behaviour

Three conventions are easy to get wrong and materially alter validation results.

**Aggregate placeholder codes are literal values, not wildcards in the data.**
`TO1` (all currencies), `UN9` (unallocated), `5J` (all countries) appear as
ordinary dimension values. The BIS consistency checks reconcile an aggregate
row against the sum of its component rows, so if these codes never appear there
is nothing to reconcile and **no check can fire**. A purely realistic dataset
(only `CAD`, `USD`, `DE`, `FR`…) is structurally incapable of exercising the
validator.

**`ISO` is a wildcard, but only inside the rulebook.** In `checks_lbs.xls` the
token `ISO` means "the reporting country's own domestic currency/country" and
matches any value on that dimension. It must never be written into data. Because
`LBS_CC:11`–`:21` target `L_CP_COUNTRY` with `ISO`, that dimension is unusable
for isolating a test scenario — the wildcard sweeps unrelated rows into the
right-hand sum. Dimensions targeted by **no** check, and therefore safe for
scenario isolation: `FREQ`, `L_MEASURE`, `L_POSITION`, `L_REP_CTY`.

**Observation semantics.** `OBS_VALUE` is signed — a negative position is an
ordinary liability direction, never a validation failure on its own. Positions
netting to exactly zero are **not reported** under SDMx convention and are
filtered after aggregation rather than published as `0`.

---

## 4. Confidentiality derivation

`OBS_CONF` is derived during micro→macro aggregation, not supplied by hand.

* **Dominance rule.** If a single reporting institution contributes more than
  `DOMINANCE_THRESHOLD` (0.60) of a cell, the cell is marked `N`.
* **Absolute contributions.** The share is `|bank| / Σ|bank|`. A signed
  denominator can reach zero on offsetting positions and yield shares above `1`,
  so signed arithmetic is not merely imprecise here — it is wrong.
* **Most-restrictive-wins rollup.** Any component `C` → `C`; else any `N` → `N`;
  else `F`.

The threshold is a **policy decision, not a value learned from data**. That is
what keeps a synthetic-only engagement honest: nothing in the build is
calibrated against real submissions.

---

## 5. Required test-case coverage

A conforming MVSD must exercise every control. Coverage below is asserted by
`tests/`; a dataset that omits a row class silently disables a test.

### 5.1 Multi-jurisdiction isolation (row-level security)

At least three reporting jurisdictions, so that "own vs. foreign" is
distinguishable and a filter that accidentally returns everything is detectable.

| `L_REP_CTY` | Sender | Purpose |
| --- | --- | --- |
| `CA` | Bank of Canada | Submitter persona under test |
| `US` | Federal Reserve System | Foreign sovereign — must stay restricted |
| `GB` | Bank of England | Third party, proves isolation is not a two-way special case |

> An earlier draft named `CH` (Switzerland) as the third jurisdiction. The corpus
> uses `GB`; `CHF` appears only as a currency denomination. Adding a fourth
> jurisdiction requires a new Entra group, a new branch in
> `fn_rls_lbs_multi_persona_lock` and new grants — it is not a data-only change.

### 5.2 Confidentiality masking

Every jurisdiction must carry **both** `OBS_CONF = 'F'` rows and
`OBS_CONF IN ('C','N')` rows at the same `TIME_PERIOD`. Without the pairing, a
mask that redacts everything and a mask that redacts nothing look identical.

The `C`/`N` rows must additionally exist in **more than one** jurisdiction. This
is what catches the cross-sovereign leak class: a mask that checks group
membership without checking segment 9 lets a Canadian analyst read US
confidential values, and a single-country corpus cannot detect it.

### 5.3 Temporal revision (SCD Type 2)

The corpus must contain a **revision of an already-published series** — the same
`(TIME_SERIES_CODE, DATE, IBS_AGG)` re-reported with a different `OBS_VALUE`.

`run_pipeline()` produces this as two ordered cycles rather than two calendar
quarters, because re-reporting the *same* period is the case that actually
stresses the state machine:

| Cycle | CA | US | GB |
| --- | --- | --- | --- |
| `baseline` | 9 rows `PUBLISHED` | 3 `PUBLISHED` | 3 `PUBLISHED` |
| `revision` | 9 rows `QUARANTINE` | 3 `PUBLISHED` | 3 `PUBLISHED` |

The assertion that matters: after both cycles Canada's *baseline* observation is
still `IS_CURRENT = true`. A rejected revision must degrade to **stale data,
never to missing data**.

> A sequential `2024-Q1 → 2024-Q2` progression tests append behaviour only. It
> never exercises expiry, so it cannot detect the failure mode where a
> quarantined revision retires the prior published record.

### 5.4 Deliberately malformed records

Because the realistic corpus cannot trigger a reconciliation check (§3), the MVSD
carries an **isolated, explicitly commented** group of rows whose sole purpose is
to fail:

| Scenario | Mechanism | Expected rule |
| --- | --- | --- |
| Aggregate ≠ Σ components | Negative amount injected into one component | `LBS_CC01` |
| Component hidden from the check | Sector code relabelled to `INVALID_SEC` so `_filter_rows` no longer matches it, while the aggregate still assumes it | `LBS_CC:04` |
| Ragged key | A `TIME_SERIES_CODE` with ≠ 11 segments | Arity guard, before any rule runs |

Two constraints on injected rows, both learned the hard way:

* The injected group's **full context tuple** must be disjoint from every
  realistic row. A realistic row sharing all dimensions except the one under
  test gets swept into the same check group and produces a spurious result. Vary
  `L_POSITION` or `L_INSTR` to keep contexts separate.
* Every other dimension of a "hidden" component must be **identical** to its
  sibling rows. A miscounted segment silently shifts all subsequent columns
  during `str.split(expand=True)` and yields a misleading non-failure.

### 5.5 Batch lifecycle states

Both terminal states must be present, since the quarantine gate is a
result-set-level control and cannot be tested from one state alone:

* `BATCH_STATUS = 'PUBLISHED'`, `QUALITY_STATUS = 'PASS'`, `FAILED_RULE_ID` null
* `BATCH_STATUS = 'QUARANTINE'`, `QUALITY_STATUS = 'FAIL'`, `FAILED_RULE_ID` a
  comma-joined sorted union of violated codes across the whole country-quarter

---

## 6. `pysdmx` integration contract

```python
from pysdmx.io import read_sdmx
from pysdmx.io.pd import PandasDataset
from pysdmx.model.dataflow import Schema
from pysdmx.io.format import Format
import pysdmx.io as sdmx_io

message = read_sdmx(BIS_LBS_DSD_URL, validate=False)
dsd = message.get_data_structure_definitions()[0]

schema = Schema(
    context="dataflow",
    agency="BIS",
    id="WS_LBS_D_PUB",
    components=dsd.components,
    version="1.0",
)
dataset = PandasDataset(structure=schema, data=frame, action=ActionType.Replace)
xml = sdmx_io.write_sdmx(dataset, Format.DATA_SDMX_ML_3_0, header=header)
```

Operational constraints:

* The `xml` extra is mandatory (`pysdmx[xml]`). Base `pysdmx` raises `ImportError`
  on read/write — and it defers that check to **call time**, so
  `from pysdmx.io import read_sdmx` succeeds and the failure surfaces from inside
  the call. Catch `ImportError` around the call, not just the import.
* `RegistryClient` speaks only SDMX-JSON 2.0.0 / Fusion-JSON. Do **not** point it
  at the BIS SDMX-ML v1 REST endpoint; use `read_sdmx(url)`.
* The frame's columns must match the DSD components exactly — 11 dimensions,
  `TIME_PERIOD`, `OBS_VALUE`, and the attributes.
* A structure-specific message is self-describing: reading one back needs no DSD.
* The live registry is a third-party dependency on the request path. Cache the
  structure for the process lifetime and keep a local writer behind it.

---

## 7. Data delivery contract

How an organisation hands over structure without handing over data.

**What is exported**

1. The DSD, as published SDMX-ML — `BIS:BIS_LBS(1.0)` is already public.
2. Codelists, as code + label pairs only.
3. The consistency rulebook — `checks_lbs.xls` is a public standards artefact.
4. Row-count magnitudes and cardinality per dimension, so synthetic volumes are
   plausible. Order of magnitude only.
5. The confidentiality threshold, as a policy parameter.

**What is never exported**

Observation values, institution identifiers, real `(country, period)` pairs from
an unpublished cycle, and any statistic tight enough to be inverted back to a
cell — including exact row counts of a confidential breakdown.

**Verification before hand-off**

* Every `OBS_VALUE` is generated, not sampled. Seeded generation is fine;
  perturbing real values is not — perturbation preserves distribution shape and
  can be attacked.
* The corpus must satisfy §5 coverage, checked by running `tests/` against it.
* No real institution names. `BANK_CA_1` is a synthetic identifier; a real LEI is
  a disclosure.

**Acceptance.** The contractor returns the generator, not the data. The
organisation re-runs it inside its own boundary and diffs the resulting schema
against production metadata. Because every control is attached to Unity Catalog
objects rather than embedded in pipeline logic, the controls activate on real
data at first run — there is no "productionisation" phase in which the security
model is re-implemented, and therefore no phase in which it can be
re-implemented incorrectly.

---

## Related skills

* [`persona_security_matrix.md`](persona_security_matrix.md) — who may read which rows
* [`sdmx_lbs_validation.md`](sdmx_lbs_validation.md) — how the rulebook is compiled and applied
* [`scd2_engine.md`](scd2_engine.md) — how revisions are historised
* [`contractor_zero_trust_workflow.md`](contractor_zero_trust_workflow.md) — the delivery pattern this dataset serves
