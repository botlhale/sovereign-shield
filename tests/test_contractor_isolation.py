"""Contractor isolation: the build must not require production access.

The delivery pattern's central claim is that an external contributor can build,
test and demonstrate the whole platform without ever holding credentials for the
system it protects. These tests assert the claim mechanically, so it degrades
loudly rather than silently.

Two directions are checked:

* **Nothing here reaches production by accident.** With no credentials present
  the code must refuse to query, not fall back to something that happens to work.
* **The offline substitutes are faithful.** A local harness that diverges from
  the deployed behaviour is worse than no harness, because it manufactures
  confidence.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

DATABRICKS_ENV = (
    "DATABRICKS_HOST",
    "DATABRICKS_SERVER_HOSTNAME",
    "DATABRICKS_TOKEN",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
    "DATABRICKS_WAREHOUSE_ID",
    "DATABRICKS_HTTP_PATH",
    "ARM_CLIENT_ID",
    "ARM_CLIENT_SECRET",
)


@pytest.fixture
def no_credentials(monkeypatch):
    """A contractor's laptop: no workspace, no tokens, no vault access."""
    for name in DATABRICKS_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SOVEREIGNSHIELD_LOCAL_DELTA", raising=False)


# ---------------------------------------------------------------------------
# Refusal rather than silent fallback
# ---------------------------------------------------------------------------


def test_unconfigured_gateway_refuses_to_query(no_credentials, monkeypatch, tmp_path):
    """With no backend the gateway raises. It does not invent one.

    The failure mode worth preventing is a query that quietly succeeds against
    something other than the governed table.
    """
    import uc_query

    monkeypatch.setattr(uc_query, "LOCAL_DELTA_ROOT", str(tmp_path / "absent"))
    gateway = uc_query.CatalogGateway()
    gateway.databricks = None
    gateway.local = None

    assert gateway.mode == "unconfigured"
    with pytest.raises(uc_query.QueryError):
        gateway.search(uc_query.SeriesFilter.build(), uc_query.PUBLIC_PRINCIPAL)


def test_databricks_backend_refuses_without_credentials(no_credentials):
    """No caller token and no service principal is a refusal, not anonymous access."""
    from uc_query import DatabricksBackend, PUBLIC_PRINCIPAL, QueryError

    backend = DatabricksBackend()
    backend.hostname = "adb-example.azuredatabricks.net"
    backend.http_path = "/sql/1.0/warehouses/deadbeef"
    backend.client_id = None
    backend.client_secret = None

    with pytest.raises(QueryError):
        backend._connect(PUBLIC_PRINCIPAL.access_token)


def test_local_mirror_is_unreachable_once_a_workspace_is_configured(monkeypatch):
    """Unity Catalog is the enforcement point wherever it is available.

    The pandas mirror exists for laptops. If it could serve requests in a
    deployed configuration it would become a policy bypass.
    """
    import importlib

    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "adb-example.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/deadbeef")

    import uc_query

    importlib.reload(uc_query)
    try:
        gateway = uc_query.CatalogGateway()
        assert gateway.mode == "unity-catalog"
        assert gateway.local is None
    finally:
        monkeypatch.undo()
        importlib.reload(uc_query)


# ---------------------------------------------------------------------------
# The offline toolchain is genuinely offline
# ---------------------------------------------------------------------------


def test_serialization_works_without_network(no_credentials, monkeypatch):
    """An unreachable BIS registry must degrade, never fail the request."""
    import sdmx_ml_exporter as sdmx

    sdmx.fetch_lbs_components.cache_clear()
    monkeypatch.setattr(sdmx, "BIS_LBS_DSD_URL", "https://127.0.0.1:9/unreachable")

    frame = pd.DataFrame(
        [
            {
                "TIME_SERIES_CODE": "Q.S.C.A.USD.F.5J.A.CA.A.5J",
                "DATE": "2026-Q1",
                "IBS_AGG": "LBSR",
                "OBS_VALUE": 100.0,
                "OBS_STATUS": "A",
                "OBS_CONF": "F",
            }
        ]
    )
    try:
        assert sdmx.fetch_lbs_components("https://127.0.0.1:9/unreachable") is None
        xml = sdmx.to_sdmx_ml_3_0(frame, validate=True)
        assert "StructureSpecificData" in xml
        assert "<Series" in xml
    finally:
        sdmx.fetch_lbs_components.cache_clear()


def test_persona_matrix_is_evaluable_without_a_workspace(corpus, visible_rows, no_credentials):
    """The security model can be exercised by someone who cannot reach the data."""
    public = visible_rows("public", corpus)
    admin = visible_rows("admin", corpus)

    assert len(public) < len(admin)
    assert (public["OBS_CONF"] == "F").all()


# ---------------------------------------------------------------------------
# The mirror tracks the metastore
# ---------------------------------------------------------------------------


def test_group_names_match_the_deployed_policy(repo_root):
    """Every group the mirror knows must exist in the DDL, and vice versa.

    This is the drift check for the one place the persona matrix is expressed
    twice. A group renamed in SQL but not in the mirror produces a local suite
    that passes while production fails closed.
    """
    import re

    from conftest import PERSONA_GROUPS

    ddl = (Path(repo_root) / "src" / "unity_catalog_triple_lock.sql").read_text(encoding="utf-8")
    in_ddl = set(re.findall(r"is_account_group_member\('([^']+)'\)", ddl))
    in_mirror = {group for groups in PERSONA_GROUPS.values() for group in groups}

    assert in_mirror <= in_ddl, f"mirror references unknown group(s): {in_mirror - in_ddl}"
    assert in_ddl <= in_mirror, f"DDL group(s) untested by the mirror: {in_ddl - in_mirror}"


def test_sovereignty_anchor_is_segment_nine(repo_root):
    """Segment 9 is L_REP_CTY across the DDL, the exporter and the query layer.

    Changing the dimension order without moving every consumer would silently
    grant a submitter another jurisdiction's rows.
    """
    import sdmx_ml_exporter as sdmx
    from uc_query import DIMENSION_SEGMENTS

    ddl = (Path(repo_root) / "src" / "unity_catalog_triple_lock.sql").read_text(encoding="utf-8")

    assert DIMENSION_SEGMENTS["L_REP_CTY"] == 9
    assert sdmx.REP_CTY_SEGMENT == 9
    assert sdmx.SDMX_DIMENSIONS[8] == "L_REP_CTY"
    assert "try_element_at(split(time_series_code, '\\\\.'), 9)" in ddl


def test_row_filter_fails_closed(repo_root):
    """The DDL must coalesce a NULL segment to FALSE, not leave it NULL."""
    ddl = (Path(repo_root) / "src" / "unity_catalog_triple_lock.sql").read_text(encoding="utf-8")

    assert "element_at(split" not in ddl.replace("try_element_at(split", ""), (
        "element_at raises INVALID_ARRAY_INDEX under ANSI mode, aborting every "
        "query against the table"
    )
    assert ddl.count("coalesce(try_element_at") >= 4


def test_no_destructive_ddl_in_the_idempotent_path(repo_root):
    """The security script runs first on every execution.

    A DROP TABLE here would erase the entire SCD2 lineage on each run and leave
    the platform unable to protect a published record from a quarantined
    revision. This regressed once already.
    """
    ddl = (Path(repo_root) / "src" / "unity_catalog_triple_lock.sql").read_text(encoding="utf-8")
    statements = [line.strip().upper() for line in ddl.splitlines()]

    assert not [s for s in statements if s.startswith("DROP TABLE")]
    assert not [s for s in statements if s.startswith("TRUNCATE")]
    assert "CREATE TABLE IF NOT EXISTS lbs_sdmx_history" in ddl
