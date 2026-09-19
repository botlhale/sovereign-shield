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
| Researcher | `sg-sovereignshield-researchers` | Published rows across jurisdictions | Explicit `F`; restricted/unknown values masked unless separately entitled |
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

## Researcher Disclosure Decision

Researchers may identify published series and request a separate agreement with
the originating authority. Registration does not grant restricted values.
Row existence, keys, confidentiality flags and counts are themselves information.
Public totals or overlapping releases can reconstruct masked values, including the
synthetic residual $1000-400-500=100$.

Invite community tests using synthetic data under the
[statistical reconstruction challenge](../../SECURITY.md#statistical-reconstruction-challenge).
Restrict or remove the Researcher role if observation existence makes inference
trivial; public-only releases also require disclosure review. Metadata catalogs
and secondary suppression are design options requiring implementation/approval,
not controls already supplied by the reference.

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
- Repeat segment 9 in the mask so an additive researcher membership cannot reveal
  a foreign restricted value to a submitter.
- Preserve genuine zero; never serialize a redacted value as zero.
- Keep rejected submissions audit-only, with the prior accepted publication current.
- Non-throwing segment lookup does not replace strict input validation or eliminate
  all privileged branches for malformed data.

## Synthetic Baseline

| Persona | Current Published Rows | Masked Values | Current Plus Quarantine Rows |
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