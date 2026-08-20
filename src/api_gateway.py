"""SovereignShield API gateway and portal host.

A single ASGI application serves both the public REST API under ``/api/v1`` and
the BIS-style portal at ``/``. Databricks Apps runs one process per app, so
splitting the API and the UI into separate runtimes would double the
deployment surface and force the UI to make a network hop back to its own host.

**Authentication is dual-mode, and neither mode carries an entitlement.**
The gateway decides *which identity* a query runs as; Unity Catalog decides
*what that identity may see*. There is no code path here that filters rows by
persona - if this file were compromised, the metastore would still refuse to
return a quarantined or confidential observation to an unentitled caller.

* **Delegated** - Databricks Apps injects ``X-Forwarded-Access-Token`` for the
  signed-in user. The token is passed through to the SQL warehouse so the row
  filter resolves against that user's own Entra ID groups. A raw
  ``Authorization: Bearer`` header is accepted equivalently, which is what makes
  the same image deployable behind Azure Container Apps.
* **Proxy** - with no token, queries run as the app's service principal
  (``spn-sovereignshield-public``), a member of ``sg-sovereignshield-public``.
  The row filter restricts it to ``BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'``.

Note on anonymity: a Databricks App always sits behind workspace SSO, so the
"public" tier there is an authenticated visitor with no sovereign entitlement.
Genuinely anonymous access requires fronting the same container with Azure
Container Apps - see ``sh/container_apps_deploy.ps1``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

# Databricks Apps and Container Apps launch this module under different names
# (`api_gateway` vs `src.api_gateway`); make the sibling modules importable either way.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sdmx_ml_exporter as sdmx  # noqa: E402
from uc_query import (  # noqa: E402
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

LOGGER = logging.getLogger(__name__)

#: Seconds an identity lookup is reused. Group membership changes propagate
#: within this window; the token itself is never cached, only its digest.
IDENTITY_TTL = int(os.getenv("SOVEREIGNSHIELD_IDENTITY_TTL", "300"))

#: Comma-separated origins allowed to call the API from a browser. Defaults to
#: same-origin only, which is all the bundled portal needs.
ALLOWED_ORIGINS = [o for o in os.getenv("SOVEREIGNSHIELD_CORS_ORIGINS", "").split(",") if o]

SOVEREIGN_SENDERS = {
    "submitter-ca": ("BOC", "Bank of Canada"),
    "submitter-us": ("FRB", "Federal Reserve System"),
}

app = FastAPI(
    title="SovereignShield Data Portal API",
    version="1.0.0",
    description=(
        "Standards-compliant access to BIS Locational Banking Statistics. "
        "Entitlement is enforced by Unity Catalog row filters and column masks, "
        "not by this service."
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
    return None


def _resolve_identity(token: str) -> Principal:
    """Validates a token by resolving the identity it represents.

    The workspace SCIM endpoint is the validator: an expired, revoked or forged
    token fails there, so no JWT signature checking is reimplemented here.
    """
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cached = _identity_cache.get(digest)
    if cached and cached[0] > time.monotonic():
        return replace(cached[1], access_token=token)

    host = os.getenv("DATABRICKS_HOST") or os.getenv("DATABRICKS_SERVER_HOSTNAME")
    if not host:
        raise HTTPException(status_code=503, detail="Workspace host is not configured.")
    if not host.startswith("http"):
        host = f"https://{host}"

    try:
        from databricks.sdk import WorkspaceClient

        me = WorkspaceClient(host=host, token=token).current_user.me()
    except Exception as exc:  # noqa: BLE001 - any failure is an auth failure
        LOGGER.info("Identity resolution rejected a caller token: %s", type(exc).__name__)
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
    _identity_cache[digest] = (time.monotonic() + IDENTITY_TTL, principal)
    return principal


def current_principal(request: Request) -> Principal:
    """FastAPI dependency resolving the caller once per request."""
    token = _extract_token(request)
    if not token:
        return PUBLIC_PRINCIPAL
    return _resolve_identity(token)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_filter(
    principal: Principal = Depends(current_principal),
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
) -> SeriesFilter:
    """Validates the filter query string once, for every route that accepts it.

    ``limit`` is deliberately left to each route: a preview table and a bulk
    export want very different defaults.
    """
    try:
        return SeriesFilter.build(
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
            include_quarantined=include_quarantined and principal.may_see_quarantine,
        )
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run(series_filter: SeriesFilter, principal: Principal):
    try:
        return gateway.search(series_filter, principal)
    except QueryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Query failed")
        raise HTTPException(status_code=502, detail=f"Catalog query failed: {exc}") from exc


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

    return {
        "access": {
            "persona": principal.persona,
            "label": principal.access_label,
            "authenticated": principal.authenticated,
        },
        "row_count": int(len(frame)),
        "masked_observations": masked,
        "truncated": len(frame) >= series_filter.limit,
        "observations": frame.where(frame.notna(), None).to_dict(orient="records"),
    }


@app.get("/api/v1/facets", tags=["data"])
def facets(principal: Principal = Depends(current_principal)):
    """Distinct code values for the filter cards, scoped to what the caller may see."""
    try:
        values = gateway.facets(sorted(set(FILTER_DIMENSIONS.values())), principal)
    except QueryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Facet query failed")
        raise HTTPException(status_code=502, detail=f"Catalog query failed: {exc}") from exc

    return {
        "dimensions": {name: values.get(dim, []) for name, dim in FILTER_DIMENSIONS.items()},
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
    frame = _run(series_filter, principal)
    if frame.empty:
        raise HTTPException(status_code=404, detail="No observations matched the filter.")

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


@app.get("/api/v1/export/sdmx-ml", tags=["export"])
def export_sdmx_ml(
    principal: Principal = Depends(current_principal),
    series_filter: SeriesFilter = Depends(search_filter),
    limit: int = Query(MAX_ROWS, ge=1, le=MAX_ROWS),
):
    """Streams the filtered series as an SDMX-ML 3.0 structure-specific message.

    The sender organisation is taken from the caller's own persona, so a Bank of
    Canada analyst's download is attributed to the Bank of Canada rather than to
    the portal that served it.
    """
    sender_id, sender_name = SOVEREIGN_SENDERS.get(
        principal.persona, ("SOVEREIGNSHIELD", "SovereignShield Data Portal")
    )
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


@app.get("/api/v1/health", tags=["service"])
def health(principal: Principal = Depends(current_principal)):
    """Catalog connectivity and structure availability."""
    status = gateway.health(principal)
    status["structure"] = sdmx.structure_urn()
    status["structure_resolved"] = sdmx.fetch_lbs_components() is not None
    status["status"] = "ok" if status.get("catalog_reachable") else "degraded"
    return status


from portal_ui import router as portal_router  # noqa: E402  (registered last, owns "/")

app.include_router(portal_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 - container workloads bind all interfaces
        port=int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000"))),
    )
