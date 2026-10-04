# Persona and Information-Access Contract

Use this reference when changing entitlements, query lifecycle or disclosure scope.
The [policy SQL](../../src/unity_catalog_triple_lock.sql) and
[query layer](../../src/uc_query.py) own the implementation.

## Identity Resolution

Unity Catalog evaluates **Databricks account-group membership** using
`is_account_group_member`. Setup reconciles selected Entra identities; it does not
continuously synchronize revocation. Workspace-local groups do not substitute for
account policy groups. Memberships compose additively.

The gateway selects SQL identity, user filters and lifecycle scope. UC applies
row/value entitlements. The gateway handles tokens and entitled results and
therefore remains trusted. Supported runtime/query paths, privileged storage,
control-plane rights and downloaded exports are separate boundaries.

## Persona Definitions

| Persona | Account Group | Row Entitlement | Measure Entitlement |
| --- | --- | --- | --- |
| Public proxy | `sg-sovereignshield-public` | Published rows explicitly `F` | Free measures only |
| Researcher (Discovery Gateway) | `sg-sovereignshield-researchers` | Published rows across jurisdictions | Explicit `F`; otherwise value NULL, key segments 10-11 `xx`, lineage NULL |
| Regional submitter | `sg-sovereignshield-submitter-ca` / `-us` | Own jurisdiction in every lifecycle state plus foreign published `F` | Own values and foreign public values |
| Administrator | `sg-sovereignshield-admin` | All countries and lifecycle history | All values through the explicit admin branch |
| No recognized membership | None | No entitled rows | No values |

The row filter does not itself require `IS_CURRENT`. The published view and
gateway's published mode select current accepted observations. An authorized base
history query can have a wider temporal scope than a standard feed.

The job's runtime service principal requires admin-group membership to read and
write governed history. Ownership alone is not a policy exemption. Run-as use
permission is a separate account rule-set grant, verified by
[configure_run_as.py](../../sh/configure_run_as.py).

## Analyst View

The Analyst View is the regional submitter workflow, not an additional group.
Its purpose is to verify that the latest filing an analyst expects the international
organization to hold matches actual submission IDs, submitted/received timestamps,
values and validation feedback. A rejected latest filing does not replace current
accepted data. Portal modes are `published`, `all` (current plus quarantine) and
`quarantine`; full accepted history requires an authorized history query.

## Researcher Discovery Gateway

Researchers learn that restricted series exist (series family, reporting country,
period and flag) so they can request an agreement with the originating authority.
They receive neither the value nor the counterparty: `fn_ddm_series_key_mask`
replaces segments 10-11 with `xx`, and `fn_ddm_lineage_mask` nulls `RECORD_ID`,
`version_hash` and `VALIDATION_NOTES`, which would otherwise re-identify the key or
confirm a guessed value. Masks resolve before predicates, facets drop the token,
and downloads exclude coordinate-masked rows, so the researcher's product equals
the public one. Restricted cells belong in a Secure Data Enclave, documented as a
concept in the White Paper; registration grants nothing.

Coordinate masking does not stop margin differencing across visible dimensions:
the fixture still yields $1000-400-500=100$, and restricted-row counts per prefix
are visible. Invite community tests under the
[statistical reconstruction challenge](../../SECURITY.md#statistical-reconstruction-challenge);
restrict or remove the role, or apply complementary suppression, where inference
is trivial.

## Educational Ledger

The modeled international intake accepts **SDMx files only**. Synthetic bank
micro-transactions exist solely to explain calculation of realistic observations.
The demo ledger is not an institutional intake requirement or system deliverable.
For demonstration, its country row filter permits administrators and own-country
submitters, with no researcher/public grants. The filing volume is administrator-only
because volumes do not carry table row filters or masks.

## Mask and History Invariants

- `OBS_VALUE` and mask input/output use `DECIMAL(38,3)`.
- Check administrator and own-country entitlements; otherwise reveal explicit `F`
  only. Missing/unknown confidentiality values return `NULL`.
- The key and lineage masks use exactly the value mask's reveal branches; a key or
  hash is never shown to a caller denied the value. Keys without 11 segments mask to `NULL`.
- Repeat segment 9 in the mask so an additive researcher membership cannot reveal
  a foreign restricted value to a submitter. Coordinate masking keeps segment 9.
- Preserve genuine zero; never serialize a redacted value as zero.
- Keep rejected submissions audit-only, with the prior accepted publication current.
- Non-throwing segment lookup does not replace strict input validation or eliminate
  all privileged branches for malformed data.

## Synthetic Baseline

| Persona | Current Published Rows | Masked Values and Keys | Current Plus Quarantine Rows |
| --- | ---: | ---: | ---: |
| Public | 13 | 0 | Quarantine request refused |
| Researcher | 22 | 9 | Quarantine request refused |
| CA submitter | 14 | 0 | 18 |
| US submitter | 17 | 0 | 21 |
| Administrator | 22 | 0 | 44 |

These are fixture outcomes, not production counts or permanent service status.
Full offboarding includes sessions/tokens, Entra/Databricks memberships, Azure,
vault, GitHub, ownership and exports; no-group data denial is only one check.
See [persona tests](../../tests/test_persona_access_matrix.py),
[live persona checks](../../sh/live_persona_checks.py) and
[the engagement contract](../../docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md).