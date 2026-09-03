# Persona & Role-Based Access Control Matrix

> **Context:** personas map to the real participants in an international statistical exchange — the submitting national central banks, the compiling body's administrators, external researchers consuming published aggregates, and the anonymous public reaching the dissemination gateway. Sovereignty between submitters is expressed as a platform constraint rather than only as an operational agreement.

## Overview

Entitlement is resolved at query time by **Unity Catalog** against **Entra ID** group membership. Because policy is attached to the table object rather than to the query, it applies identically through PySpark, a SQL warehouse, Power BI, an ad-hoc JDBC session, or the public REST gateway. No code path can omit it.

**Namespace:** `dbw_sovereignshield.sovereign_shield`

---

## The controlling principle

> **The gateway chooses an identity. It never chooses rows.**

`src/api_gateway.py` decides *which principal* a query runs as. Unity Catalog decides *what that principal may see*. There is no persona branch anywhere in the serving code — the SQL it builds is deliberately naive about confidentiality and lifecycle state. If the gateway were compromised outright, the metastore would still refuse to return a quarantined or confidential observation to an unentitled caller.

The single exception is `LocalDeltaBackend` in `src/uc_query.py`, a development mirror that reimplements this matrix in pandas so the platform can be demonstrated and regression-tested with no workspace attached. It is unreachable whenever `DATABRICKS_SERVER_HOSTNAME` is set.

---

## Persona definitions

### 0. Execution identity — CI/CD service principal

* **Principal:** `spn-sovereignshield-cicd`
* **Role:** pipeline orchestrator and implicit owner of every created object.
* **Mandatory membership:** `sg-sovereignshield-admin`.

> Ownership does **not** exempt a principal from a row filter. The SCD2 engine reads the history table to locate records it must expire; if the filter hid those rows the merge would see an empty target, treat every incoming row as new, and silently duplicate history without ever closing prior versions. No exception is raised — only the lineage is corrupted.

No human developer holds DDL rights in production. All structural change passes through version control and is deployed by this identity.

### 1. Anonymous public consumer

* **Entra ID group:** `sg-sovereignshield-public`
* **Reaches:** `lbs_sdmx_history` (filtered), `v_lbs_sdmx_published`
* **Entitlement:** `BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'` across all jurisdictions — strictly clean, free-to-publish data.

The public tier is an **explicit group, not the absence of one**. The row filter fails closed, so "unauthenticated" cannot be a fall-through case; it would return zero rows. The dissemination gateway's proxy principal is a member of this group, which makes the anonymous entitlement auditable in Entra ID like any other.

> On Databricks Apps this persona is an authenticated workspace visitor holding no sovereign entitlement, because a Databricks App always sits behind SSO. Genuinely anonymous access is demonstrated by the Azure Container Apps deployment, which fronts the same image with external ingress.

### 2. Authenticated researcher

* **Entra ID group:** `sg-sovereignshield-researchers`
* **Reaches:** `lbs_sdmx_history` (filtered), `v_lbs_sdmx_published`
* **Entitlement:** `BATCH_STATUS = 'PUBLISHED'` across all jurisdictions — including confidential series, whose `OBS_VALUE` arrives masked to `NULL`.

Researchers see the confidential *rows*, not the confidential *values*. This preserves structural dimensional density: joins still resolve and dimensional counts stay correct, while the protected metric is withheld. `NULL` is the international convention for a redacted observation, and it is also the only option available — a mask must return the masked column's own type, and `OBS_VALUE` is a `DOUBLE`, so a `'xxx'` sentinel is not representable.

Quarantined batches remain invisible: an unvalidated figure must never reach a research citation.

### 3. Regional reporting submitter

* **Entra ID group:** `sg-sovereignshield-submitter-<cc>` (`-ca`, `-us`)
* **Reaches:** `lbs_sdmx_history` **and** the raw `lbs_micro_transactions` ledger
* **Entitlement, own jurisdiction:** every record where segment 9 of `TIME_SERIES_CODE` equals their ISO code — including `QUARANTINE` batches and `C`/`N` confidential values, unmasked.
* **Entitlement, foreign jurisdictions:** only `BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'`. Foreign confidential records stay restricted; foreign quarantined records are invisible.

Quarantine visibility is not a convenience — a submitter cannot diagnose a rejected submission without seeing the rejected rows and their `FAILED_RULE_ID`.

Micro-ledger access is defence in depth. Protecting the aggregate while leaving the unaggregated, institution-identifying source open is not sovereignty. Neither researchers nor the public tier are granted anything on that table.

### 4. Central auditor / platform administrator

* **Entra ID group:** `sg-sovereignshield-admin`
* **Reaches:** every object
* **Entitlement:** `1 = 1`. All jurisdictions, all lifecycle states, all confidentiality levels, unmasked — including historical SCD2 rows (`VALID_FROM`, `VALID_TO`, `IS_CURRENT = false`).

### Fail-closed default

A principal with no recognised membership resolves to `FALSE` — zero rows.

> Off-boarding a contractor and enforcing sovereignty between two nations are **the same code path**. There is no separate revocation feature that could rot, be forgotten, or be tested less rigorously than the primary one.

---

## Enforcement objects

![The Unity Catalog policy enforcement point: the row filter and column mask signatures above a persona list — public (published and free only), researcher (published, values masked), submitter (own jurisdiction in full), auditor (unrestricted), and no group (zero rows, fails closed).](../../docs/sovereign-shield_technical_vision.jpg)

*The right-hand column of this diagram is the table below, drawn. The dimmed
final row is the fail-closed default — the one entry that makes the other four
safe to grant.*

| Lock | Object | Binding | Granularity |
| --- | --- | --- | --- |
| RLS (macro) | `fn_rls_lbs_multi_persona_lock` | `WITH ROW FILTER ... ON (TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF)` | Row |
| RLS (micro) | `fn_rls_micro_country_lock` | `WITH ROW FILTER ... ON (reporting_country)` | Row |
| DDM | `fn_ddm_obs_conf_mask` | `OBS_VALUE DOUBLE MASK ... USING COLUMNS (OBS_CONF, TIME_SERIES_CODE)` | Cell |
| Quarantine view | `v_lbs_sdmx_published` | `BATCH_STATUS = 'PUBLISHED' AND IS_CURRENT = true` | Result set |

### Why the row filter reads three columns

Filtering on the SDMx key alone was sufficient while the platform was internal. It stops being sufficient the moment the data is publicly reachable: a public visitor asking for Canadian series would receive Canada's quarantined and confidential rows as readily as its published ones. Sovereignty, lifecycle state and confidentiality have to be evaluated in the same predicate.

```sql
CREATE OR REPLACE FUNCTION fn_rls_lbs_multi_persona_lock(
  time_series_code STRING, batch_status STRING, obs_conf STRING
)
RETURNS BOOLEAN
RETURN
  is_account_group_member('sg-sovereignshield-admin')
  OR (is_account_group_member('sg-sovereignshield-researchers')
      AND upper(coalesce(batch_status, '')) = 'PUBLISHED')
  OR ((is_account_group_member('sg-sovereignshield-public')
       OR is_account_group_member('sg-sovereignshield-submitter-ca')
       OR is_account_group_member('sg-sovereignshield-submitter-us'))
      AND upper(coalesce(batch_status, '')) = 'PUBLISHED'
      AND upper(coalesce(obs_conf, '')) = 'F')
  OR (is_account_group_member('sg-sovereignshield-submitter-ca')
      AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'CA', FALSE))
  OR (is_account_group_member('sg-sovereignshield-submitter-us')
      AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'US', FALSE));
```

Four details are load-bearing:

* **Tiers compose with `OR`, not `CASE`.** A `CASE` stops at its first matching branch, so an analyst who is also a researcher would be silently downgraded to whichever branch happened to be written first. Disjunction makes entitlement additive — a principal receives the union of their memberships.
* **`try_element_at`, never `element_at`.** Under ANSI mode an out-of-range index raises `INVALID_ARRAY_INDEX`. A row filter runs on every row of every query, so one malformed key would abort **all** access to the table, converting a data-quality defect into an outage.
* **`coalesce(..., FALSE)`.** `try_element_at` returns `NULL` for a ragged key; without the coalesce the predicate is `NULL` and the row's visibility depends on how the optimiser folds it. Explicitly failing closed makes a malformed row invisible rather than universally visible.
* **Case normalisation on both sides.** A lowercase code must not evade the filter.

### Why the mask reads the key

```sql
CREATE OR REPLACE FUNCTION fn_ddm_obs_conf_mask(
  obs_val DOUBLE, obs_conf STRING, time_series_code STRING
)
RETURNS DOUBLE
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') THEN obs_val
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca')
    AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'CA', FALSE) THEN obs_val
  WHEN is_account_group_member('sg-sovereignshield-submitter-us')
    AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'US', FALSE) THEN obs_val
  WHEN upper(coalesce(obs_conf, '')) IN ('C', 'N') THEN NULL
  ELSE obs_val
END;
```

Without `TIME_SERIES_CODE` the function knows a value is confidential but not *whose* it is. Any submitter membership would then unmask every jurisdiction's restricted cells — a Bank of Canada analyst reading Federal Reserve confidential positions. The mask therefore repeats the segment-9 test rather than trusting the group name alone.

> **Provenance.** This was a genuine defect in an early draft of the mask in this
> repository — not a hypothetical, and not something that ever reached a
> deployment. It was written, then caught during development on synthetic data by
> the multi-jurisdiction fixture and a mutation check on the test that was
> supposed to cover it. That is the reason §5.2 of the MVSD specification requires
> confidential rows in more than one jurisdiction: a single-country corpus cannot
> detect it, and the first test written for it passed against the broken mask.

### A note on views

A Unity Catalog view resolves group membership against the **view owner**, not the caller. Per-caller entitlement must therefore be evaluated against the base table, which is why the gateway queries `lbs_sdmx_history` directly rather than serving from a pre-filtered view. `v_lbs_sdmx_published` remains a convenience for BI tools with a uniform audience.

---

## Summary matrix

| Persona | Entra ID group | Rows visible | `OBS_VALUE` | Micro ledger | Quarantine |
| --- | --- | --- | --- | --- | --- |
| CI/CD | `spn-sovereignshield-cicd` | All (via admin group) | Raw | Yes | Yes |
| Public | `sg-sovereignshield-public` | `PUBLISHED` + `OBS_CONF = 'F'` | Raw (only `F` visible) | No | No |
| Researcher | `sg-sovereignshield-researchers` | `PUBLISHED`, all jurisdictions | `C`/`N` → `NULL` | No | No |
| Submitter `<cc>` | `sg-sovereignshield-submitter-<cc>` | Own segment 9 in full; foreign `PUBLISHED` + `F` | Raw for own; masked for foreign | Own country only | Own only |
| Admin / auditor | `sg-sovereignshield-admin` | `1 = 1` | Raw | Yes | Yes |
| *(no membership)* | — | **None** | — | No | No |

---

## Deployment prerequisites

1. Groups must exist at the Databricks **account** level. `is_account_group_member` does not resolve workspace-scoped groups, which look identical in the UI and silently match nothing.
2. `spn-sovereignshield-cicd` must be in `sg-sovereignshield-admin`.
3. The dissemination gateway's own managed service principal must be in `sg-sovereignshield-public`. On Databricks Apps this is a Databricks-managed principal distinct from the Entra `spn-sovereignshield-public`, which serves the Container Apps deployment.
4. Compute must run `data_security_mode: USER_ISOLATION`. Unity Catalog will not evaluate RLS or DDM on `SINGLE_USER` compute.

---

## Related skills

* [`triple_lock_security.md`](triple_lock_security.md) — the enforcement objects in detail
* [`mvsd_specification.md`](mvsd_specification.md) — the corpus that makes this matrix testable
* [`contractor_zero_trust_workflow.md`](contractor_zero_trust_workflow.md) — how the matrix survives contractor off-boarding
