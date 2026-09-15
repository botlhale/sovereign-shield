"""Public Dissemination Gateway & Multi-Tenant Consumer Tier.

A single ASGI application serving both the public REST API under ``/api/v1`` and
the BIS-style portal at ``/``. Databricks Apps runs one process per app, so
splitting them into separate runtimes would double the deployment surface and
force the UI to make a network hop back to its own host.

**Two-tier consumption model.**

* **Tier 1, anonymous.** No token. Queries run as the app's own service
  principal, a member of ``sg-sovereignshield-public``, which the Unity Catalog
  row filter restricts to ``BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'``.
* **Tier 2, authenticated.** A caller token is passed through to the SQL
  warehouse, so the row filter and column mask resolve against that caller's own
  Entra ID groups and the elevated personas unlock.

The gateway selects the SQL identity and lifecycle query. Unity Catalog enforces
table-level entitlement. The gateway handles bearer tokens and entitled results,
so its integrity remains trusted; a compromise is not harmless.

Token carriers, in precedence order:

* ``X-Forwarded-Access-Token`` - injected by the Databricks Apps runtime for the
  signed-in user (on-behalf-of).
* ``X-MS-TOKEN-AAD-ACCESS-TOKEN`` - used when Azure Container Apps injects it.
    Otherwise the portal reads same-origin ``/.auth/me`` and sends the provider
    token as an in-memory bearer token.
* ``Authorization: Bearer`` - a direct API client.

Credentials are never read from a literal. The app's own identity arrives as
platform-injected environment references; on Container Apps those resolve from
Key Vault through a managed identity. Terraform-managed secret values still
reside in sensitive state and saved plans.

Note on anonymity: a Databricks App always sits behind workspace SSO, so the
"public" tier there is an authenticated visitor with no sovereign entitlement.
Genuinely anonymous access requires fronting the same container with Azure
Container Apps - see ``terraform/modules/dissemination_gateway`` or
``sh/container_apps_deploy.ps1``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Databricks Apps and Container Apps launch this module under different names
# (`api_gateway` vs `src.api_gateway`); make the sibling modules importable either way.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sdmx_ml_exporter as sdmx  # noqa: E402
from uc_query import (  # noqa: E402
    AUDIT_COLUMNS,
    DEFAULT_ROWS,
    DIMENSION_SEGMENTS,
    FILTER_DIMENSIONS,
    MAX_ROWS,
    PUBLIC_PRINCIPAL,
    CatalogGateway,
    Principal,
    QueryError,
    SeriesFilter,
)
from decimal_measures import decimal_text

LOGGER = logging.getLogger(__name__)

#: Seconds an identity lookup is reused. Group membership changes propagate
#: within this window; the token itself is never cached, only its digest.
IDENTITY_TTL = int(os.getenv("SOVEREIGNSHIELD_IDENTITY_TTL", "300"))

#: Comma-separated origins allowed to call the API from a browser. Defaults to
#: same-origin only, which is all the bundled portal needs.
ALLOWED_ORIGINS = [o for o in os.getenv("SOVEREIGNSHIELD_CORS_ORIGINS", "").split(",") if o]

SOVEREIGN_SENDERS = {
    "submitter-ca": ("SUBMITTER_CA", "Canadian Regional Submitter (CA)"),
    "submitter-us": ("SUBMITTER_US", "US Regional Submitter (US)"),
}


def _json_records(frame):
    """Convert pandas missing values to JSON nulls for API responses."""
    records = frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
    for record in records:
        if record.get("OBS_VALUE") is not None:
            record["OBS_VALUE"] = decimal_text(record["OBS_VALUE"])
    return records

DEFAULT_SENDER = ("SOVEREIGNSHIELD", "SovereignShield Dissemination Gateway")

app = FastAPI(
    title="SovereignShield Public Dissemination Gateway",
    version="1.0.0",
    description=(
        "Reference dissemination of synthetic BIS LBS-shaped observations, "
        "served from 100% synthetic data. Entitlement is enforced by Unity Catalog "
        "row filters and column masks, not by this service."
    ),
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization"],
    )

gateway = CatalogGateway()

_identity_cache: Dict[str, Tuple[float, Principal]] = {}
_identity_lock = Lock()
IDENTITY_CACHE_MAX = 512


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization, Cookie, X-Forwarded-Access-Token, X-MS-TOKEN-AAD-ACCESS-TOKEN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _extract_token(request: Request) -> Optional[str]:
    """Pulls the caller's OAuth token from any of the supported carriers."""
    # Databricks Apps (on-behalf-of-user), then Azure Container Apps built-in
    # authentication, then a plain bearer token from a direct API client.
    for header in ("X-Forwarded-Access-Token", "X-MS-TOKEN-AAD-ACCESS-TOKEN"):
        forwarded = request.headers.get(header)
        if forwarded:
            return forwarded.strip()

    authorization = request.headers.get("Authorization", "")
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() == "bearer" and credential.strip():
        return credential.strip()

    # Container Apps always injects trusted identity headers after Easy Auth
    # login, but provider tokens are retrieved through /.auth/me when the Blob
    # token store is enabled rather than injected on every request.
    if request.headers.get("X-MS-CLIENT-PRINCIPAL"):
        stored_token = _easy_auth_access_token(request)
        if stored_token:
            return stored_token

    return None


def _easy_auth_identities(request: Request) -> List[Dict[str, Any]]:
    """Read signed-in identities from the Easy Auth token store."""
    cookie = request.headers.get("cookie")
    if not cookie:
        return []

    external_url = os.getenv("SOVEREIGNSHIELD_EXTERNAL_URL", "").rstrip("/")
    if not external_url:
        host = request.url.hostname or ""
        if not host.endswith(".azurecontainerapps.io"):
            return []
        external_url = f"https://{host}"

    token_request = urllib.request.Request(
        f"{external_url}/.auth/me",
        headers={"Cookie": cookie, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(token_request, timeout=5) as response:
            identities = json.load(response)
    except Exception as exc:  # noqa: BLE001 - authentication falls back closed
        LOGGER.warning("Easy Auth token-store lookup failed: %s", type(exc).__name__)
        return []

    return [identity for identity in identities if isinstance(identity, dict)] \
        if isinstance(identities, list) else []


def _easy_auth_access_token(request: Request) -> Optional[str]:
    """Read the signed-in user's provider token from the Easy Auth token store."""
    identities = _easy_auth_identities(request)

    for identity in identities:
        access_token = identity.get("access_token")
        if access_token:
            return str(access_token).strip()
    return None


def _resolve_identity(token: str) -> Principal:
    """Validates a token by resolving the identity it represents.

    The workspace SCIM endpoint is the validator: an expired, revoked or forged
    token fails there, so no JWT signature checking is reimplemented here.
    """
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _identity_lock:
        now = time.monotonic()
        for key in [key for key, entry in _identity_cache.items() if entry[0] <= now]:
            del _identity_cache[key]
        cached = _identity_cache.get(digest)
        if cached:
            return replace(cached[1], access_token=token)

    host = os.getenv("DATABRICKS_HOST") or os.getenv("DATABRICKS_SERVER_HOSTNAME")
    if not host:
        raise HTTPException(status_code=503, detail="Workspace host is not configured.")
    if not host.startswith("http"):
        host = f"https://{host}"

    try:
        from databricks.sdk import WorkspaceClient

        # auth_type is pinned rather than left to inference. Databricks Apps injects
        # DATABRICKS_CLIENT_ID/SECRET for the app's own service-principal identity,
        # so the ambient environment always has a second viable credential sitting
        # next to the caller's token. The SDK's unified auth resolver sees both and
        # raises rather than guessing which one the caller intended - "more than one
        # authorization method configured" - which this code was swallowing into an
        # indistinguishable 401 on every call, for every caller, always.
        me = WorkspaceClient(host=host, token=token, auth_type="pat").current_user.me()
    except Exception as exc:  # noqa: BLE001 - any failure is an auth failure
        LOGGER.warning("Identity resolution rejected a caller token: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid or expired access token.") from exc

    groups = frozenset(
        (group.display or "").lower() for group in (me.groups or []) if group.display
    )
    principal = Principal(
        display_name=me.display_name or me.user_name or "Authenticated user",
        groups=groups,
        authenticated=True,
        access_token=token,
    )
    with _identity_lock:
        while len(_identity_cache) >= IDENTITY_CACHE_MAX:
            _identity_cache.pop(next(iter(_identity_cache)))
        _identity_cache[digest] = (time.monotonic() + IDENTITY_TTL, replace(principal, access_token=None))
    return principal


def current_principal(request: Request) -> Principal:
    """FastAPI dependency resolving the caller once per request."""
    token = _extract_token(request)
    if not token:
        if request.headers.get("X-MS-CLIENT-PRINCIPAL"):
            raise HTTPException(status_code=401, detail="Signed-in credentials are unavailable. Sign in again.")
        return PUBLIC_PRINCIPAL
    return _resolve_identity(token)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_filter(
    principal: Principal = Depends(current_principal),
    frequency: Optional[List[str]] = Query(None, description="FREQ code(s): A annual, S semi-annual, Q quarterly, M monthly"),
    parent_country: Optional[List[str]] = Query(None, description="L_PARENT_CTY code(s), e.g. CA, 5J"),
    reporting_country: Optional[List[str]] = Query(None, description="L_REP_CTY code(s) - the reporting sovereign"),
    counterpart_sector: Optional[List[str]] = Query(None, description="L_CP_SECTOR code(s), e.g. B, N, A"),
    counterpart_country: Optional[List[str]] = Query(None, description="L_CP_COUNTRY code(s)"),
    currency: Optional[List[str]] = Query(None, description="L_DENOM code(s), e.g. CAD, USD, TO1"),
    position: Optional[List[str]] = Query(None, description="L_POSITION code(s): C claims, L liabilities"),
    instrument: Optional[List[str]] = Query(None, description="L_INSTR code(s)"),
    date_from: Optional[str] = Query(None, description="Inclusive lower bound, e.g. 2026-Q1"),
    date_to: Optional[str] = Query(None, description="Inclusive upper bound, e.g. 2026-Q4"),
    include_quarantined: bool = Query(False, description="Include the caller's own quarantined batches"),
    lifecycle: Optional[str] = Query(None, pattern="^(published|all|quarantine)$"),
) -> SeriesFilter:
    """Validates the filter query string once, for every route that accepts it.

    ``limit`` is deliberately left to each route: a preview table and a bulk
    export want very different defaults.
    """
    try:
        selection = SeriesFilter.build(
            frequency=frequency,
            parent_country=parent_country,
            reporting_country=reporting_country,
            counterpart_sector=counterpart_sector,
            counterpart_country=counterpart_country,
            currency=currency,
            position=position,
            instrument=instrument,
            date_from=date_from,
            date_to=date_to,
            # Asking for quarantine is not the same as being allowed it. The row
            # filter would drop the rows regardless; this keeps the query honest
            # rather than relying on the metastore to clean up after the API.
            include_quarantined=include_quarantined,
            lifecycle=lifecycle,
        )
        if selection.view_mode != "published" and not principal.may_see_quarantine:
            raise HTTPException(status_code=403, detail="Quarantine views require a submitter or administrator identity.")
        return selection
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run(series_filter: SeriesFilter, principal: Principal):
    try:
        frame = gateway.search(series_filter, principal)
        return frame if principal.may_see_quarantine else frame.drop(columns=AUDIT_COLUMNS, errors="ignore")
    except QueryError as exc:
        raise HTTPException(status_code=503, detail="The catalog is unavailable or not configured.") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Query failed")
        raise HTTPException(status_code=502, detail="Catalog query failed.") from exc


@app.get("/api/v1/search", tags=["data"])
def search(
    principal: Principal = Depends(current_principal),
    series_filter: SeriesFilter = Depends(search_filter),
    limit: int = Query(DEFAULT_ROWS, ge=1, le=MAX_ROWS, description="Preview page size"),
):
    """Filters the governed time-series history as the calling persona."""
    series_filter = replace(series_filter, limit=limit)
    frame = _run(series_filter, principal)
    masked = int(frame["OBS_VALUE"].isna().sum()) if "OBS_VALUE" in frame.columns else 0
    # Databricks SQL NULLs arrive in numeric pandas columns as NaN. Convert to
    # object dtype before replacing missing values; otherwise pandas preserves
    # NaN and Starlette rejects the response as non-JSON-compliant.
    observations = _json_records(frame)

    return {
        "access": {
            "persona": principal.persona,
            "label": principal.access_label,
            "authenticated": principal.authenticated,
        },
        "row_count": int(len(frame)),
        "masked_observations": masked,
        "truncated": len(frame) >= series_filter.limit,
        "observations": observations,
    }


@app.get("/api/v1/facets", tags=["data"])
def facets(principal: Principal = Depends(current_principal)):
    """Distinct code values for the filter cards, scoped to what the caller may see."""
    try:
        values = gateway.facets(sorted(set(FILTER_DIMENSIONS.values())), principal)
        periods = gateway.periods(principal)
    except QueryError as exc:
        raise HTTPException(status_code=503, detail="The catalog is unavailable or not configured.") from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Facet query failed")
        raise HTTPException(status_code=502, detail="Catalog query failed.") from exc

    return {
        "dimensions": {name: values.get(dim, []) for name, dim in FILTER_DIMENSIONS.items()},
        "reference_periods": periods,
        "segments": DIMENSION_SEGMENTS,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _export(
    wire_format: str,
    series_filter: SeriesFilter,
    principal: Principal,
    **serializer_kwargs,
) -> Response:
    if wire_format.startswith("sdmx-") and series_filter.view_mode != "published":
        raise HTTPException(status_code=400, detail="Standard SDMx exports require the Published view. Use audit CSV for quarantine records.")
    frame = _run(series_filter, principal)
    if frame.empty:
        return Response(status_code=204)

    try:
        payload, media_type, extension = sdmx.serialize(frame, wire_format, **serializer_kwargs)
    except sdmx.SdmxSerializationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"sovereignshield_lbs_{stamp}.{extension}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-SovereignShield-Persona": principal.persona,
            "X-SovereignShield-Rows": str(len(frame)),
        },
    )


@app.get("/api/v1/export/audit-csv", tags=["export"])
def export_audit_csv(
    principal: Principal = Depends(current_principal),
    series_filter: SeriesFilter = Depends(search_filter),
    limit: int = Query(MAX_ROWS, ge=1, le=MAX_ROWS),
):
    return _export("audit-csv", replace(series_filter, limit=limit), principal)


@app.get("/api/v1/export/sdmx-ml", tags=["export"])
def export_sdmx_ml(
    principal: Principal = Depends(current_principal),
    series_filter: SeriesFilter = Depends(search_filter),
    limit: int = Query(MAX_ROWS, ge=1, le=MAX_ROWS),
):
    """Streams the filtered series as an SDMX-ML 3.0 structure-specific message.

    The sender identifies the caller's synthetic jurisdiction persona, not an
    official statistical institution.
    """
    sender_id, sender_name = SOVEREIGN_SENDERS.get(principal.persona, DEFAULT_SENDER)
    return _export(
        "sdmx-ml",
        replace(series_filter, limit=limit),
        principal,
        sender_id=sender_id,
        sender_name=sender_name,
        validate=True,
    )


@app.get("/api/v1/export/sdmx-json", tags=["export"])
def export_sdmx_json(
    principal: Principal = Depends(current_principal),
    series_filter: SeriesFilter = Depends(search_filter),
    limit: int = Query(MAX_ROWS, ge=1, le=MAX_ROWS),
):
    """Streams the filtered series as an SDMX-JSON 2.0.0 data message."""
    return _export("sdmx-json", replace(series_filter, limit=limit), principal)


@app.get("/api/v1/export/csv", tags=["export"])
def export_csv(
    principal: Principal = Depends(current_principal),
    series_filter: SeriesFilter = Depends(search_filter),
    limit: int = Query(MAX_ROWS, ge=1, le=MAX_ROWS),
    format: str = Query("sdmx", pattern="^(sdmx|tidy)$", description="sdmx = SDMX-CSV 2.0.0"),
):
    """Streams the filtered series as SDMX-CSV 2.0.0, or plain tidy CSV on request."""
    return _export(
        "sdmx-csv" if format == "sdmx" else "tidy-csv",
        replace(series_filter, limit=limit),
        principal,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@app.get("/api/v1/whoami", tags=["service"])
def whoami(principal: Principal = Depends(current_principal)):
    """The security context the portal banner renders."""
    return {
        "display_name": principal.display_name,
        "authenticated": principal.authenticated,
        "persona": principal.persona,
        "label": principal.access_label,
        "groups": sorted(principal.groups),
        "may_see_quarantine": principal.may_see_quarantine,
    }


@app.get("/api/v1/auth-diagnostics", tags=["service"])
def auth_diagnostics(request: Request):
    """Reports trusted platform auth-header presence without exposing values."""
    trusted_headers = (
        "X-Forwarded-Access-Token",
        "X-MS-TOKEN-AAD-ACCESS-TOKEN",
        "X-MS-TOKEN-AAD-ID-TOKEN",
        "X-MS-CLIENT-PRINCIPAL",
        "X-MS-CLIENT-PRINCIPAL-ID",
        "X-MS-CLIENT-PRINCIPAL-NAME",
    )
    identities = _easy_auth_identities(request) if request.headers.get("X-MS-CLIENT-PRINCIPAL") else []
    return {
        "headers_present": [name for name in trusted_headers if request.headers.get(name)],
        "authorization_present": bool(request.headers.get("Authorization")),
        "easy_auth_identity_count": len(identities),
        "easy_auth_access_token_present": any(bool(identity.get("access_token")) for identity in identities),
        "easy_auth_id_token_present": any(bool(identity.get("id_token")) for identity in identities),
    }


@app.get("/api/v1/health", tags=["service"])
def health(principal: Principal = Depends(current_principal)):
    """Catalog connectivity and structure availability."""
    status = gateway.health(principal)
    status["structure"] = sdmx.structure_urn()
    status["structure_resolved"] = bool(sdmx.pinned_components())
    status["status"] = "ok" if status.get("catalog_reachable") else "degraded"
    return status


from portal_ui import router as portal_router  # noqa: E402  (registered last, owns "/")

app.include_router(portal_router)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), check_dir=False), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 - container workloads bind all interfaces
        port=int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000"))),
    )
