# Spec: Restore persona sign-in on the Container Apps portal

- **Intent:** [intent.md](intent.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-08
- **Approved by:** @botlhale, 2026-10-08 (request to fix the live environment)
- **Skills applied:** `cloud-lifecycle`, `evidence-and-claims`

## Requirements

- **R1.** The deploy script writes the login parameter in the Azure CLI list syntax,
  which no shell alters. It then reads the parameter back and fails unless the
  stored value is exactly `scope=openid profile offline_access
  2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/user_impersonation`.
- **R2.** The script declares the Azure Databricks permission only when it is
  missing. It grants admin consent for every scope the sign-in requests:
  - Microsoft Graph: `openid profile email offline_access`;
  - Azure Databricks: `user_impersonation`.
- **R3.** Stage 8 reads the live sign-in redirect without following it, and fails
  unless Entra ID is asked for the Azure Databricks scope.
- **R4.** When the portal's signed-in session is refused, it renews the provider
  token once through `/.auth/refresh` and retries. If the session is still
  refused, it offers "Sign out" and says why.
- **R5.** With an empty `SOVEREIGNSHIELD_SIGNOUT_URL`, the Databricks App's
  configuration, the portal shows no sign-out link. It shows that the session comes
  from workspace single sign-on.
- **R6.** A refused token is logged with its audience, never its value.
- **R7.** The live environment gets the corrected parameter and consent and a
  de-duplicated permission list. Both portals are redeployed through Stages 3 and
  5 to 8, and the Stage 8 checks pass.
- **R8.** Each defect has a regression test. The scope defect also becomes an eval
  case.

## Design

- **Login parameter.** `--set "…loginParameters=[$expected]"`. The CLI strips the
  brackets and splits on commas, so the value needs no quotes on any platform.
- **Consent.** `az ad app permission grant` replaces the grant for its resource,
  so repeating it is idempotent.
- **Redirect check.** `HttpClient` with `AllowAutoRedirect = $false`, because
  PowerShell 7's `-MaximumRedirection 0` throws on a redirect.
- **Portal.** A single `offerSignOut()` decides between the sign-out link and the
  single sign-on label.
- **Redeployment.** Stage 3 uploads the bundle source. Starting at Stage 5, not 6,
  makes Stage 6 deploy a new app snapshot instead of reconciling the previous one.
  Stage 4 is skipped, so no synthetic filing is ingested again.

## Flagged concerns

| Concern | Policy owner | Resolution |
| --- | --- | --- |
| Admin consent for `offline_access` lets the portal hold refresh tokens in its Blob token store | @botlhale (security) | Accepted. The sign-in already requested it; consent removes per-user prompts and enables token renewal. The store is private and separate from governed data |
| A Databricks App cannot sign a user out of workspace single sign-on, so switching personas there needs a separate browser session | @botlhale (product) | Accepted and documented in the runbook; the Container Apps portal is the persona-switching surface |

## Acceptance criteria

| Requirement | Proof |
| --- | --- |
| R1, R2, R3 | `tests/test_deployment_boundaries.py` checks the list syntax, the read-back, the guarded permission, both consent grants and the Stage 8 redirect check |
| R4, R5, R6 | `tests/test_api_gateway.py` checks the refresh-and-retry, the sign-out decision, the app configuration and the audience log |
| R7 | The live redirect requests the Azure Databricks scope. Stages 5 to 8 complete. The owner signs in as a persona and sees entitled data |
| R8 | Full offline suite; `evals/run_evals.py --self-test` includes the new case |

## Out of scope

- The bash quick-start script, which already tells the operator to set the
  parameter by hand.
- The `databricks-sql` token-federation warnings logged for every query. They are
  noise: the connector falls back to the presented token.
