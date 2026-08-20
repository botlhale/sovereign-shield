"""Query layer between the portal and the governed Delta history.

Every read goes to ``lbs_sdmx_history`` **as the caller**, never through a
pre-filtered view, because the Unity Catalog row filter and column mask are the
only things deciding what a persona may see. A Unity Catalog view resolves
group membership against the view owner, so filtering in a view would hand
every visitor the owner's entitlement.

Nothing here re-implements the persona matrix against the warehouse: the SQL
this module builds is deliberately naive about confidentiality, and the
metastore narrows the result. The one exception is :class:`LocalDeltaBackend`,
a development mirror used when no workspace is reachable.

Two connection modes:

* **on-behalf-of** - a caller's OAuth token is passed straight through, so
  Unity Catalog evaluates the filter against their Entra ID groups
* **public proxy** - the app's own service principal, a member of
  ``sg-sovereignshield-public``, which the row filter restricts to published
  free-to-publish observations
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

LOGGER = logging.getLogger(__name__)

CATALOG = os.getenv("SOVEREIGNSHIELD_CATALOG", "dbw_sovereignshield")
SCHEMA = os.getenv("SOVEREIGNSHIELD_SCHEMA", "sovereign_shield")
HISTORY_TABLE = os.getenv(
    "SOVEREIGNSHIELD_HISTORY_TABLE", f"{CATALOG}.{SCHEMA}.lbs_sdmx_history"
)
LOCAL_DELTA_ROOT = os.getenv("SOVEREIGNSHIELD_LOCAL_DELTA", "data/local_delta_catalog")

#: Segment position (1-based) of each filterable dimension inside TIME_SERIES_CODE.
DIMENSION_SEGMENTS: Dict[str, int] = {
    "FREQ": 1,
    "L_MEASURE": 2,
    "L_POSITION": 3,
    "L_INSTR": 4,
    "L_DENOM": 5,
    "L_CURR_TYPE": 6,
    "L_PARENT_CTY": 7,
    "L_REP_BANK_TYPE": 8,
    "L_REP_CTY": 9,
    "L_CP_SECTOR": 10,
    "L_CP_COUNTRY": 11,
}

#: Portal filter name -> SDMx dimension.
FILTER_DIMENSIONS: Dict[str, str] = {
    "parent_country": "L_PARENT_CTY",
    "reporting_country": "L_REP_CTY",
    "counterpart_sector": "L_CP_SECTOR",
    "counterpart_country": "L_CP_COUNTRY",
    "currency": "L_DENOM",
    "position": "L_POSITION",
    "instrument": "L_INSTR",
}

RESULT_COLUMNS: List[str] = [
    "TIME_SERIES_CODE",
    "DATE",
    "IBS_AGG",
    "OBS_VALUE",
    "OBS_STATUS",
    "OBS_CONF",
    "QUALITY_STATUS",
    "BATCH_STATUS",
    "IS_CURRENT",
]

MAX_ROWS = int(os.getenv("SOVEREIGNSHIELD_MAX_ROWS", "20000"))
DEFAULT_ROWS = 500

#: SDMx code values are short alphanumerics. Anything else is rejected before it
#: reaches the warehouse - parameter binding already prevents injection, this
#: keeps malformed input from being blamed on the metastore.
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,12}$")
_PERIOD_PATTERN = re.compile(r"^\d{4}(-(Q[1-4]|S[1-2]|(0[1-9]|1[0-2])))?$")


class QueryError(ValueError):
    """Raised when a request cannot be turned into a safe query."""


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesFilter:
    """A validated portal search request."""

    dimensions: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    include_quarantined: bool = False
    limit: int = DEFAULT_ROWS

    @classmethod
    def build(
        cls,
        *,
        parent_country: Optional[Sequence[str]] = None,
        reporting_country: Optional[Sequence[str]] = None,
        counterpart_sector: Optional[Sequence[str]] = None,
        counterpart_country: Optional[Sequence[str]] = None,
        currency: Optional[Sequence[str]] = None,
        position: Optional[Sequence[str]] = None,
        instrument: Optional[Sequence[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        include_quarantined: bool = False,
        limit: int = DEFAULT_ROWS,
    ) -> "SeriesFilter":
        raw = {
            "parent_country": parent_country,
            "reporting_country": reporting_country,
            "counterpart_sector": counterpart_sector,
            "counterpart_country": counterpart_country,
            "currency": currency,
            "position": position,
            "instrument": instrument,
        }
        dimensions: Dict[str, Tuple[str, ...]] = {}
        for name, values in raw.items():
            codes = _clean_codes(name, values)
            if codes:
                dimensions[FILTER_DIMENSIONS[name]] = codes

        return cls(
            dimensions=dimensions,
            date_from=_clean_period("date_from", date_from),
            date_to=_clean_period("date_to", date_to),
            include_quarantined=include_quarantined,
            limit=_clean_limit(limit),
        )


def _clean_codes(name: str, values: Optional[Sequence[str]]) -> Tuple[str, ...]:
    if not values:
        return ()
    cleaned = []
    for value in values:
        for part in str(value).split(","):
            code = part.strip().upper()
            if not code:
                continue
            if not _CODE_PATTERN.match(code):
                raise QueryError(f"'{code}' is not a valid {name} code.")
            if code not in cleaned:
                cleaned.append(code)
    return tuple(cleaned)


def _clean_period(name: str, value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    period = str(value).strip().upper()
    if not _PERIOD_PATTERN.match(period):
        raise QueryError(f"{name} must look like '2026', '2026-Q1' or '2026-03', got '{value}'.")
    return period


def _clean_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError) as exc:
        raise QueryError(f"limit must be an integer, got '{limit}'.") from exc
    if parsed < 1:
        raise QueryError("limit must be at least 1.")
    return min(parsed, MAX_ROWS)


# ---------------------------------------------------------------------------
# SQL construction
# ---------------------------------------------------------------------------


def _segment(dimension: str) -> str:
    """SQL expression extracting one dimension from the composite key.

    ``try_element_at`` rather than ``element_at``: under ANSI mode an
    out-of-range index aborts the whole query instead of yielding NULL.
    """
    return f"try_element_at(split(TIME_SERIES_CODE, '\\\\.'), {DIMENSION_SEGMENTS[dimension]})"


def build_search_sql(series_filter: SeriesFilter) -> Tuple[str, Dict[str, Any]]:
    """Builds the parameterised search statement and its bind values.

    Only generated identifiers are interpolated; every caller-supplied value is
    bound.
    """
    predicates: List[str] = []
    parameters: Dict[str, Any] = {}

    if series_filter.include_quarantined:
        # Quarantined revisions are written closed (IS_CURRENT = false) so they
        # can never supersede a published value; they are surfaced only on request.
        predicates.append("(IS_CURRENT = true OR BATCH_STATUS = 'QUARANTINE')")
    else:
        predicates.append("IS_CURRENT = true")

    for dimension, codes in series_filter.dimensions.items():
        markers = []
        for position, code in enumerate(codes):
            marker = f"{dimension.lower()}_{position}"
            parameters[marker] = code
            markers.append(f":{marker}")
        predicates.append(f"{_segment(dimension)} IN ({', '.join(markers)})")

    if series_filter.date_from:
        parameters["date_from"] = series_filter.date_from
        predicates.append("DATE >= :date_from")
    if series_filter.date_to:
        parameters["date_to"] = series_filter.date_to
        predicates.append("DATE <= :date_to")

    projection = ",\n       ".join(
        RESULT_COLUMNS + [f"{_segment(d)} AS {d}" for d in DIMENSION_SEGMENTS]
    )
    where_clause = "\n   AND ".join(predicates)
    sql = (
        f"SELECT {projection}\n"
        f"  FROM {HISTORY_TABLE}\n"
        f" WHERE {where_clause}\n"
        f" ORDER BY TIME_SERIES_CODE, DATE\n"
        f" LIMIT {series_filter.limit}"
    )
    return sql, parameters


def build_facet_sql(dimension: str) -> str:
    """Builds the distinct-value query backing one filter card.

    The result is already persona-scoped: a visitor cannot discover that a code
    exists if the row filter hides every row carrying it.
    """
    if dimension not in DIMENSION_SEGMENTS:
        raise QueryError(f"Unknown dimension '{dimension}'.")
    return (
        f"SELECT DISTINCT {_segment(dimension)} AS CODE\n"
        f"  FROM {HISTORY_TABLE}\n"
        f" WHERE IS_CURRENT = true\n"
        f"   AND {_segment(dimension)} IS NOT NULL\n"
        f" ORDER BY CODE"
    )


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    """Who a request is running as, and what the portal should tell them."""

    display_name: str
    groups: frozenset
    authenticated: bool
    access_token: Optional[str] = None

    @property
    def persona(self) -> str:
        if "sg-sovereignshield-admin" in self.groups:
            return "admin"
        for iso in ("ca", "us"):
            if f"sg-sovereignshield-submitter-{iso}" in self.groups:
                return f"submitter-{iso}"
        if "sg-sovereignshield-researchers" in self.groups:
            return "researcher"
        return "public"

    @property
    def access_label(self) -> str:
        return {
            "admin": "Platform Administrator (All Jurisdictions)",
            "submitter-ca": "Bank of Canada Analyst (Full Sovereign Access)",
            "submitter-us": "Federal Reserve Analyst (Full Sovereign Access)",
            "researcher": "Researcher (Published Series, Confidential Values Masked)",
            "public": "Public (Free to Publish Only)",
        }[self.persona]

    @property
    def may_see_quarantine(self) -> bool:
        return self.persona in {"admin", "submitter-ca", "submitter-us"}


PUBLIC_PRINCIPAL = Principal(
    display_name="Anonymous",
    groups=frozenset({"sg-sovereignshield-public"}),
    authenticated=False,
)


class DatabricksBackend:
    """Runs queries against a Databricks SQL warehouse."""

    def __init__(self) -> None:
        self.hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME") or _host_from_env()
        self.http_path = os.getenv("DATABRICKS_HTTP_PATH") or _http_path_from_warehouse()
        self.client_id = os.getenv("DATABRICKS_CLIENT_ID")
        self.client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")

    @property
    def configured(self) -> bool:
        return bool(self.hostname and self.http_path)

    def _connect(self, access_token: Optional[str]):
        from databricks import sql

        if not self.configured:
            raise QueryError(
                "Databricks connectivity is not configured; set DATABRICKS_SERVER_HOSTNAME "
                "and DATABRICKS_HTTP_PATH (or DATABRICKS_WAREHOUSE_ID)."
            )

        if access_token:
            # On-behalf-of: Unity Catalog evaluates the row filter against the
            # caller's own Entra ID groups.
            return sql.connect(
                server_hostname=self.hostname,
                http_path=self.http_path,
                access_token=access_token,
            )

        if not (self.client_id and self.client_secret):
            raise QueryError(
                "No caller token and no public service principal credentials "
                "(DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET)."
            )

        from databricks.sdk.core import Config, oauth_service_principal

        config = Config(
            host=f"https://{self.hostname}",
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        return sql.connect(
            server_hostname=self.hostname,
            http_path=self.http_path,
            credentials_provider=lambda: oauth_service_principal(config),
        )

    def query(
        self, sql_text: str, parameters: Dict[str, Any], principal: Principal
    ) -> pd.DataFrame:
        with self._connect(principal.access_token) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql_text, parameters=parameters or None)
                columns = [description[0] for description in cursor.description]
                return pd.DataFrame(cursor.fetchall(), columns=columns)


class LocalDeltaBackend:
    """Development mirror over the local Delta tables under ``data/``.

    This is the one place the persona matrix is expressed twice. Unity Catalog
    is the enforcement point in every deployed configuration; this class exists
    so the portal can be demonstrated, and the matrix regression-tested, on a
    laptop with no workspace attached. It is never reachable when
    ``DATABRICKS_SERVER_HOSTNAME`` is set.
    """

    def __init__(self, root: str = LOCAL_DELTA_ROOT) -> None:
        self.root = root
        self._frame: Optional[pd.DataFrame] = None

    @property
    def configured(self) -> bool:
        return os.path.isdir(self.root)

    def _load(self) -> pd.DataFrame:
        if self._frame is not None:
            return self._frame

        from deltalake import DeltaTable

        frames = []
        for entry in sorted(os.listdir(self.root)):
            path = os.path.join(self.root, entry)
            if os.path.isdir(os.path.join(path, "_delta_log")):
                frames.append(DeltaTable(path).to_pandas())
        if not frames:
            raise QueryError(f"No local Delta tables found under '{self.root}'.")

        frame = pd.concat(frames, ignore_index=True)
        frame.columns = [
            {
                "effective_start_date": "VALID_FROM",
                "effective_end_date": "VALID_TO",
                "is_current": "IS_CURRENT",
            }.get(column, column)
            for column in frame.columns
        ]
        for column in RESULT_COLUMNS:
            if column not in frame.columns:
                frame[column] = pd.NA
        frame["OBS_VALUE"] = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
        self._frame = frame
        return frame

    def query(
        self, sql_text: str, parameters: Dict[str, Any], principal: Principal
    ) -> pd.DataFrame:
        raise NotImplementedError("LocalDeltaBackend is driven by search()/facets() directly.")

    def search(self, series_filter: SeriesFilter, principal: Principal) -> pd.DataFrame:
        frame = self._apply_persona(self._load(), principal)

        if series_filter.include_quarantined and principal.may_see_quarantine:
            mask = (frame["IS_CURRENT"] == True) | (frame["BATCH_STATUS"] == "QUARANTINE")  # noqa: E712
        else:
            mask = frame["IS_CURRENT"] == True  # noqa: E712
        frame = frame[mask]

        for dimension, codes in series_filter.dimensions.items():
            position = DIMENSION_SEGMENTS[dimension] - 1
            segment = frame["TIME_SERIES_CODE"].astype(str).str.split(".").str[position]
            frame = frame[segment.isin(codes)]

        if series_filter.date_from:
            frame = frame[frame["DATE"].astype(str) >= series_filter.date_from]
        if series_filter.date_to:
            frame = frame[frame["DATE"].astype(str) <= series_filter.date_to]

        frame = frame.sort_values(["TIME_SERIES_CODE", "DATE"]).head(series_filter.limit)
        return _with_dimension_columns(frame.reset_index(drop=True))

    def facets(self, dimension: str, principal: Principal) -> List[str]:
        frame = self._apply_persona(self._load(), principal)
        frame = frame[frame["IS_CURRENT"] == True]  # noqa: E712
        position = DIMENSION_SEGMENTS[dimension] - 1
        segment = frame["TIME_SERIES_CODE"].astype(str).str.split(".").str[position]
        return sorted({value for value in segment.dropna().tolist() if value})

    @staticmethod
    def _apply_persona(frame: pd.DataFrame, principal: Principal) -> pd.DataFrame:
        """Mirrors fn_rls_lbs_multi_persona_lock and fn_ddm_obs_conf_mask."""
        frame = frame.copy()
        reporting = frame["TIME_SERIES_CODE"].astype(str).str.split(".").str[8]
        published = frame["BATCH_STATUS"].astype(str).str.upper() == "PUBLISHED"
        free = frame["OBS_CONF"].astype(str).str.upper() == "F"
        groups = principal.groups

        visible = pd.Series(False, index=frame.index)
        if "sg-sovereignshield-admin" in groups:
            visible |= True
        if "sg-sovereignshield-researchers" in groups:
            visible |= published
        if groups & {
            "sg-sovereignshield-public",
            "sg-sovereignshield-submitter-ca",
            "sg-sovereignshield-submitter-us",
        }:
            visible |= published & free
        own = pd.Series(False, index=frame.index)
        for iso in ("CA", "US"):
            if f"sg-sovereignshield-submitter-{iso.lower()}" in groups:
                own |= reporting == iso
        visible |= own

        frame = frame[visible].copy()
        own = own[visible]

        if "sg-sovereignshield-admin" not in groups:
            restricted = frame["OBS_CONF"].astype(str).str.upper().isin(["C", "N"]) & ~own
            frame.loc[restricted, "OBS_VALUE"] = float("nan")
        return frame


def _with_dimension_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS + list(DIMENSION_SEGMENTS))
    frame = frame.copy()
    segments = frame["TIME_SERIES_CODE"].astype(str).str.split(".", expand=True)
    for dimension, position in DIMENSION_SEGMENTS.items():
        frame[dimension] = segments[position - 1] if position - 1 in segments.columns else pd.NA
    return frame[[c for c in RESULT_COLUMNS if c in frame.columns] + list(DIMENSION_SEGMENTS)]


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class CatalogGateway:
    """Selects a backend once and serves every portal read through it."""

    def __init__(self) -> None:
        databricks = DatabricksBackend()
        self.databricks = databricks if databricks.configured else None
        local = LocalDeltaBackend()
        self.local = local if (self.databricks is None and local.configured) else None
        if self.databricks is None and self.local is None:
            LOGGER.warning(
                "Neither a Databricks warehouse nor a local Delta catalog is reachable; "
                "search requests will fail until one is configured."
            )

    @property
    def mode(self) -> str:
        if self.databricks is not None:
            return "unity-catalog"
        if self.local is not None:
            return "local-delta"
        return "unconfigured"

    def search(self, series_filter: SeriesFilter, principal: Principal) -> pd.DataFrame:
        if self.databricks is not None:
            sql_text, parameters = build_search_sql(series_filter)
            return self.databricks.query(sql_text, parameters, principal)
        if self.local is not None:
            return self.local.search(series_filter, principal)
        raise QueryError("No data backend is configured.")

    def facets(self, dimensions: Sequence[str], principal: Principal) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for dimension in dimensions:
            if self.databricks is not None:
                frame = self.databricks.query(build_facet_sql(dimension), {}, principal)
                result[dimension] = [c for c in frame["CODE"].tolist() if c]
            elif self.local is not None:
                result[dimension] = self.local.facets(dimension, principal)
            else:
                raise QueryError("No data backend is configured.")
        return result

    def health(self, principal: Principal) -> Dict[str, Any]:
        status: Dict[str, Any] = {"backend": self.mode, "table": HISTORY_TABLE}
        try:
            probe = SeriesFilter.build(limit=1)
            rows = self.search(probe, principal)
            status["catalog_reachable"] = True
            status["rows_visible_to_caller"] = int(len(rows))
        except Exception as exc:  # noqa: BLE001 - health must never raise
            status["catalog_reachable"] = False
            status["detail"] = str(exc)
        return status


def _host_from_env() -> Optional[str]:
    host = os.getenv("DATABRICKS_HOST")
    if not host:
        return None
    return host.replace("https://", "").replace("http://", "").rstrip("/")


def _http_path_from_warehouse() -> Optional[str]:
    warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
    return f"/sql/1.0/warehouses/{warehouse_id}" if warehouse_id else None
