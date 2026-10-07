# Solution Audit

**Scope:** the working tree of 1 October 2026: commit `a1cc707` plus the Discovery Gateway,
documentation and bring-your-own-estate changes committed with this audit. The review read
every Markdown document, the reference notes in `.github/skills/`, all source, scripts and
tests. Offline verification on Linux (Python 3.14.4) recorded **245 passed, 12 skipped**; the
skips are opt-in live and stress tests. The local demo, a researcher persona fixture, the
figure renders and the Markdown link check were run. No cloud resource was created, changed
or read. This replaces the historical audit of commit `1d09269`; its findings are tracked in
[Resolution of the Historical Audit](#resolution-of-the-historical-audit). The readiness,
publication and legal sections were revised on 4 October 2026 for an educational,
knowledge-sharing publication strategy; the technical findings are unchanged.

## Findings at This Revision

1. **High: live acceptance of the Discovery Gateway masks is outstanding.** The policy plane
   now binds five column masks, including one on the merge key `RECORD_ID`. They are verified
   against the SQL contract and the local mirror only. Databricks documents `MERGE` support
   for deterministic, non-nested masks such as these, but until `verify_synthetic_runtime`
   and [live_persona_checks.py](../sh/live_persona_checks.py) pass on a workspace, every
   publication must say "tested offline". The
   [acceptance gate](RELEASE_EVIDENCE.md#discovery-gateway-acceptance) lists the checks and a
   fallback.
2. **High: coordinate masking does not stop margin differencing.** In the local fixture the
   researcher sees `Q.S.C.A.UN9.U.5J.A.CA.xx.xx` as restricted, yet the public CA total
   (1000), domestic currency (400) and foreign currency (500) give $1000-400-500=100$
   exactly. The mask hides the counterparty, not a residual across visible dimensions.
   Before real data, the release product needs complementary suppression, for example with
   sdcTable or tau-ARGUS, or the totals must be withheld.
3. **High, fixed in this revision: lineage side channels.** `version_hash` hashed the measure
   with attributes a researcher can read, so any guessed value, such as the residual above,
   could be confirmed exactly through direct SQL. `RECORD_ID` hashes the submission ID and full
   key, so the new coordinate mask could have been undone by enumerating 20 sectors x 432 areas,
   8,640 candidates. `fn_ddm_lineage_mask` now withholds both, and `VALIDATION_NOTES`, under the
   value's reveal rule. `SOURCE_SHA256`, a whole-file digest, is not practically invertible.
4. **Medium: the Discovery Gateway reveals counts.** Restricted rows stay one per cell, so the
   portal and direct SQL show how many restricted cells share a nine-segment prefix and period.
   Counts tell an attacker how many cells a residual is spread across. Serve researchers a
   curated view that collapses restricted rows to one "restricted series exists" flag per
   prefix and period.
5. **Medium: every persona holds base-table SELECT.** The gateway queries as the caller, so
   researcher and public groups can also query `agg_sdmx_history` directly. Masks protect the
   values, but the surface is wider than the portal: submission IDs, timestamps and counts.
   Grant researcher and public groups a view, and keep the base table for submitters, the
   administrator and the runtime identity.
6. **Medium: jurisdictions are hard-coded.** Twelve `is_account_group_member` branches for CA
   and US span five policy functions; each new reporting country is a policy release.
   Databricks now recommends attribute-based access control, governed tags with `CREATE
   POLICY`, for consistent row filters and masks across tables. Evaluate it before scaling
   beyond the demonstration.
7. **Medium, fixed in this revision: the greenfield lifecycle was Windows-bound.**
   `sovereignshield_up.ps1` now resolves the virtual environment's Python on either platform
   and hands the token-store SAS to `az` without `cmd.exe`, so the greenfield path runs in
   PowerShell 7 (`pwsh`) on Linux. The recorded reference runs used Windows; macOS is untested.
8. **Medium: the bring-your-own-estate scripts are stub-tested.** Nine offline tests prove
   attach-before-create, tagging, sticky provenance, typed confirmation, tag-checked teardown
   and dependency order against stub `az` and `databricks` executables. Run `--dry-run`
   against a sandbox subscription, then one full up and down, before recommending them.
9. **Low: residual live-registry code.** `fetch_lbs_components` and the ElementTree writer in
   [sdmx_ml_exporter.py](../src/sdmx_ml_exporter.py), the validator's lazy `dsd` property and
   `fetch_bis_lbs_dsd` in the generator are unused on runtime paths but contradict the
   pinned-contract rule. Remove them or move them behind the refresh helper.
10. **Low: revocation latency.** The gateway caches resolved identities for 300 seconds, so a
    removed membership can persist that long for an active session.
11. **Low: identifiers and history.** `.vscode/tasks.json` carried the Databricks account ID,
    tenant domain and resource names of a torn-down deployment; this revision stops tracking
    it. These are not secrets, but they remain in history, as does the bootstrap password of
    commit `af8cf06`; the owner confirmed on 1 October 2026 that it was reset.

## Resolution of the Historical Audit

| Finding at `1d09269` | Status now | Evidence |
| --- | --- | --- |
| P0 bootstrap password in history | Resolved: the script generates a password per run, and the exposed credential was reset (owner-confirmed, 1 October 2026); history keeps the inert value | [grp_users_create.sh](../sh/grp_users_create.sh) |
| P0 policy deployment could fail open | Resolved: immutable content-addressed functions, no detach, errors propagate, bindings verified | [Policy tests](../tests/test_policy_deployment.py); live run of 15 September |
| P0 plan-only CI with deployment rights | Mitigated: pull requests have no cloud federation; plan and deploy need a manual run on `main` behind an environment with independent, non-self reviewers | [promote.yml](../.github/workflows/promote.yml); live GitHub settings not inspected |
| High masking is not inference protection | Open by design and documented; narrowed by coordinate masking, lineage masking and releasable-only downloads | Finding 2; [security challenge](../SECURITY.md#statistical-reconstruction-challenge) |
| High unknown classifications exposed values | Resolved: pinned codelists at intake; every mask reveals explicit `F` only | [Input tests](../tests/test_input_contract.py) |
| High export integrity | Resolved: exact `DECIMAL(38,3)`, duplicate keys refused, separate audit CSV, masked keys refused | [Wire tests](../tests/test_sdmx_validation_rules.py) |
| High SCD2 not transactional | Resolved for the single writer: one MERGE per filing, replay is a no-op; distributed writers untested | [History tests](../tests/test_submission_history.py); live run of 15 September |
| High scaling claim not wired | Resolved: governed `policy_id` and approval flag; pandas parsing remains driver-bound | [compute.tf](../terraform/modules/databricks_workspace/compute.tf) |
| Launch blocker: CI and lifecycle claims | Partly resolved: state-derived readiness, lifecycle lock, stage recovery; current CI status not inspected | [Deployment tests](../tests/test_deployment_boundaries.py) |

## Readiness Score

**Overall: 7/10 for educational publication on LinkedIn and in an archive**, up from 5/10. It
rises to 8 once finding 1 passes live. This is not a production-readiness score: real
confidential data needs findings 2, 4 and 5 resolved and institutional acceptance.

| Evaluation | Score | Assessment |
| --- | ---: | --- |
| Entitlement enforcement | 8/10 | Additive row filter, fail-closed masks, segment-9 re-check, coordinate and lineage masks; direct base-table access is wider than needed |
| Declarative separation | 8/10 | One writer per object; Terraform grants, bundle policies, verified bindings |
| Temporal and SDMx integrity | 8/10 | Pinned contract, 21 rules, atomic MERGE, exact decimals, standard feeds published-only |
| Statistical disclosure | 5/10 | Honest and testable, but margins remain open and counts are visible |
| Lifecycle engineering | 7/10 | Greenfield proven live; bring-your-own estate stub-tested; greenfield runs on Windows and Linux `pwsh`, macOS untested |
| Documentation | 8/10 | One README, consolidated runbook, removed duplicates, modern figures; publications still dense |
| Institutional and IP boundary | 7/10 | Clear notices and a reset history credential; `LICENSE` and `NOTICE` name Botlhale Mosweu as sole copyright holder |
| Publication readiness | 7/10 | Strong story and evidence; until finding 1 passes live, coordinate masking is described as tested offline |

## Design Challenges

- **The user specification keyed masking on `CONF = 'N'` or `OBS_STATUS = 'C'`.** `C` is not
  in `CL_OBS_STATUS(1.0)`, and `CONF = 'N'` alone would expose `C`, `D` and `S` cells. The masks
  withhold every observation not explicitly `F`, including unknown and missing codes.
- **Discovery belongs in a product, not a side effect.** A curated discovery view (finding 4)
  is easier to approve than reasoning about every column of the base table.
- **Treat suppression as a release step.** Run complementary suppression on the public product
  and test it with the reconstruction challenge, rather than relying on access control.
- **Parameterize the catalog.** `dbw_sovereignshield` is fixed across the policy SQL, bundle,
  gateway and scripts; an existing estate may need its own naming convention.
- **Keep the enclave conceptual until it has an owner.** Output checking, agreements and
  network isolation are operating commitments, not code. Databricks Clean Rooms suit
  multi-authority analysis.

## Publication Assessment

**Worth publishing as educational practitioner evidence rather than a new invention or a pitch.**
Row filters, column masks, SDMx tooling, synthetic data and secure enclaves all exist. What is
uncommon is a working, reproducible integration for international statistical exchange with
the limits stated in public: synthetic-first delivery for contractors and AI agents, a
submitter reconciliation view, coordinate masking with its side channels closed, and a
reconstruction counter-example. That candour is the differentiator with senior readers.

- **Lead with one idea.** The Discovery Gateway and the "masking a value but leaving its hash"
  lesson are the most shareable; the full pattern belongs in the article body.
- **Narrow audience, high signal.** SDMx, central-bank statistics and Unity Catalog readers
  are a small group; expect quality conversations rather than reach. A three-part series,
  contractor dilemma, Discovery Gateway, analyst reconciliation, builds standing more
  reliably than one long post. Transferable lessons, such as entitlement-aware retrieval for
  AI assistants, widen the audience without diluting the evidence.
- **Teach, don't sell.** Service offers, rates or calls to hire would undercut the
  independence notice and the candour readers value; collaboration proposals follow credibility.
- **Avoid** "novel", "guarantee", "air-gapped" and "zero trust" as a selling point, naming an
  employer outside the independence notice, any internal system description, and speculation
  about which cloud an international organization uses. The [LinkedIn plan](LINKEDIN_POST.md)
  carries a draft that follows these rules.

## Legal Boundaries

Repository inspection cannot certify provenance, ownership or employment compliance; the
author remains responsible for them. Describe experience generically. Third-party standards
files keep their publishers' terms. `LICENSE` and `NOTICE` name Botlhale Mosweu as the
sole copyright holder. Disclose AI assistance where a venue requires it, using the
[AI-assisted SDLC disclosure](../CONTRIBUTING.md#ai-assisted-software-development-life-cycle).
