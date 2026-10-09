# Intent: Restore persona sign-in on the Container Apps portal

- **Status:** implemented
- **Originator:** @botlhale, after signing in as personas on the 8 October deployment
- **Product owner:** @botlhale
- **Date:** 2026-10-08
- **Source:** incident

## Problem

On the live deployment, every persona that signs in to the Container Apps portal
is refused. `/api/v1/whoami` answers 401 and the gateway logs "Identity resolution
rejected a caller token: BadRequest". Only the anonymous public tier works. The
Databricks App serves every persona, but its "Sign out" link leaves the user
signed in.

Evidence gathered on 8 October 2026:

- Easy Auth's sign-in redirect asks Entra ID for `scope=openid profile email` and
  adds a second, malformed parameter `"scope=openid profile offline_access
  2ff814a6-…/user_impersonation"`. The stored login parameter kept the JSON quotes
  that `sh/container_apps_deploy.ps1` wrote: PowerShell 7 on Linux passes them to
  `az`, while Windows strips them. Entra therefore issues Microsoft Graph tokens.
- The workspace answers HTTP 400 to a Graph token and 200 to an Azure Databricks
  token for the same operator, which matches the logged BadRequest.
- After a refused sign-in the portal offers only "Sign in", which reuses the same
  session, so the visitor cannot leave it.
- On the Databricks App, "Sign out" points to `/`, because a Databricks App has no
  sign-out of its own.
- Every deployment adds another copy of the Azure Databricks permission to the
  portal app registration (17 copies). `offline_access`, which the sign-in requests,
  has no admin consent.

## Proposed outcome

Personas who sign in to the Container Apps portal see their entitled data, on a
deployment made from Linux or Windows. A deployment that would send the wrong scope
fails before the operator finds out by signing in. A refused or expired session
offers a working way out. The Databricks App no longer offers a sign-out it cannot
perform.

## Affected users and systems

- Persona users of both portals.
- `sh/container_apps_deploy.ps1`, Stage 8 of `sh/sovereignshield_up.ps1`,
  `src/templates/portal.html`, `src/app.yaml`, `src/api_gateway.py`.
- The live Container App's authentication settings and the
  `app-sovereignshield-portal` app registration and its consent grants.

## Constraints

- The anonymous public tier and the Unity Catalog policy files stay unchanged.
- No token or secret is printed, logged or committed.
- Live changes are limited to the portal's sign-in configuration, its app
  registration and consent, and redeploying both portals through the lifecycle
  stages. The ingestion pipeline is not rerun.

## Open questions

Answered by the product owner on 8 October 2026: fix the live environment now and
commit the changes.
