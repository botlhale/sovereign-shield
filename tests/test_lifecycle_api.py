import csv
import io
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api_gateway as api
from uc_query import (
    PUBLIC_PRINCIPAL, LocalDeltaBackend, Principal, SeriesFilter, build_search_sql, coordinate_masked,
)


@pytest.fixture
def client(monkeypatch, corpus):
    backend = LocalDeltaBackend()
    frame = corpus.copy()
    frame["SUBMISSION_ID"] = frame["BATCH_STATUS"].map({"PUBLISHED": "accepted", "QUARANTINE": "rejected"})
    frame["FAILED_RULE_ID"] = frame["BATCH_STATUS"].map({"PUBLISHED": None, "QUARANTINE": "LBS_CC:04"})
    frame["BATCH_FAILED_RULE_ID"] = frame["FAILED_RULE_ID"]
    frame["RECEIVED_AT"] = pd.Timestamp("2026-01-01", tz="UTC")
    monkeypatch.setattr(backend, "_load", lambda: frame.copy())
    monkeypatch.setattr(api, "gateway", SimpleNamespace(search=backend.search))
    api.app.dependency_overrides[api.current_principal] = lambda: Principal(
        display_name="admin", groups=frozenset({"sg-sovereignshield-admin"}), authenticated=True,
    )
    with TestClient(api.app) as client:
        yield client
    api.app.dependency_overrides.clear()


def test_quarantine_only_returns_failure_feedback(client):
    response = client.get("/api/v1/search?lifecycle=quarantine")
    assert response.status_code == 200
    rows = response.json()["observations"]
    assert rows and all(row["BATCH_STATUS"] == "QUARANTINE" for row in rows)
    assert rows[0]["FAILED_RULE_ID"] == "LBS_CC:04"
    assert rows[0]["SUBMISSION_ID"] == "rejected"
    assert rows[0]["OBS_VALUE"] == "99.000"
    assert response.headers["cache-control"] == "private, no-store"


def test_audit_export_preserves_lifecycle_records(client):
    response = client.get("/api/v1/export/audit-csv?lifecycle=all")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == int(response.headers["x-sovereignshield-rows"])
    assert {row["SUBMISSION_ID"] for row in rows} == {"accepted", "rejected"}
    assert "FAILED_RULE_ID" in rows[0]


@pytest.mark.parametrize("path", ["sdmx-ml", "sdmx-json", "csv?format=sdmx"])
def test_standard_export_rejects_audit_mode(client, path):
    separator = "&" if "?" in path else "?"
    response = client.get(f"/api/v1/export/{path}{separator}lifecycle=all")
    assert response.status_code == 400
    assert "audit CSV" in response.json()["detail"]


def test_researcher_cannot_request_quarantine(client):
    api.app.dependency_overrides[api.current_principal] = lambda: Principal(
        display_name="researcher", groups=frozenset({"sg-sovereignshield-researchers"}), authenticated=True,
    )
    assert client.get("/api/v1/search?lifecycle=quarantine").status_code == 403
    rows = client.get("/api/v1/search").json()["observations"]
    assert "FAILED_RULE_ID" not in rows[0]
    assert any(row["OBS_VALUE"] is None for row in rows)


def _as_researcher():
    api.app.dependency_overrides[api.current_principal] = lambda: Principal(
        display_name="researcher", groups=frozenset({"sg-sovereignshield-researchers"}), authenticated=True,
    )


def test_discovery_gateway_preview_reports_masked_coordinates(client):
    _as_researcher()
    payload = client.get("/api/v1/search").json()
    masked = [row for row in payload["observations"] if row["OBS_VALUE"] is None]

    assert payload["masked_coordinates"] == payload["masked_observations"] == len(masked) > 0
    assert all(row["TIME_SERIES_CODE"].endswith(".xx.xx") for row in masked)
    assert all(row["L_CP_SECTOR"] == row["L_CP_COUNTRY"] == "xx" for row in masked)


@pytest.mark.parametrize("path", ["sdmx-ml", "sdmx-json", "csv?format=sdmx", "audit-csv"])
def test_researcher_downloads_contain_releasable_observations_only(client, path):
    """Discovery metadata stays in the portal; downloads equal the public product."""
    _as_researcher()
    preview = client.get("/api/v1/search").json()
    researcher = client.get(f"/api/v1/export/{path}")
    api.app.dependency_overrides[api.current_principal] = lambda: PUBLIC_PRINCIPAL
    public = client.get(f"/api/v1/export/{path}")

    assert researcher.status_code == public.status_code == 200
    assert int(researcher.headers["x-sovereignshield-rows"]) == preview["row_count"] - preview["masked_coordinates"]
    assert researcher.headers["x-sovereignshield-rows"] == public.headers["x-sovereignshield-rows"]
    assert ".xx" not in researcher.text and "\"xx\"" not in researcher.text
    if "csv" in path:
        assert researcher.text == public.text


def test_restricted_rows_never_consume_the_download_limit(client):
    """Masked keys sort first in this fixture; releasable rows must still fill the limit."""
    _as_researcher()
    researcher = client.get("/api/v1/export/csv?format=sdmx&limit=2")
    api.app.dependency_overrides[api.current_principal] = lambda: PUBLIC_PRINCIPAL
    public = client.get("/api/v1/export/csv?format=sdmx&limit=2")

    assert researcher.status_code == 200
    assert researcher.headers["x-sovereignshield-rows"] == "2"
    assert researcher.text == public.text


def test_fully_restricted_download_is_no_content_with_withheld_count(client):
    _as_researcher()
    response = client.get("/api/v1/export/sdmx-json?reporting_country=US&position=L")

    assert response.status_code == 204
    assert response.headers["x-sovereignshield-withheld"] == "1"


def test_empty_standard_export_is_no_content(client):
    assert client.get("/api/v1/export/sdmx-json?reporting_country=ZZ").status_code == 204


def test_download_query_drops_masked_keys_before_its_limit():
    sql, _ = build_search_sql(replace(SeriesFilter.build(limit=5), releasable_only=True))
    where = sql.split(" WHERE ", 1)[1].split(" ORDER BY ", 1)[0]

    assert "TIME_SERIES_CODE NOT LIKE '%.xx.xx'" in where
    assert "NOT LIKE" not in build_search_sql(SeriesFilter.build())[0]


def test_local_download_drops_a_key_the_mask_withheld_entirely(corpus, monkeypatch):
    """A malformed restricted key masks to NULL, which SQL NOT LIKE excludes; the mirror must agree."""
    frame = corpus.copy()
    frame.loc[frame["TIME_SERIES_CODE"].str.contains(".CAD.", regex=False), "TIME_SERIES_CODE"] = "Q.S.C.A"
    backend = LocalDeltaBackend()
    monkeypatch.setattr(backend, "_load", lambda: frame.copy())
    researcher = Principal(display_name="researcher", groups=frozenset({"sg-sovereignshield-researchers"}),
                           authenticated=True)

    preview = backend.search(SeriesFilter.build(), researcher)
    download = backend.search(replace(SeriesFilter.build(), releasable_only=True), researcher)

    assert preview["TIME_SERIES_CODE"].isna().sum() == 1
    assert download["TIME_SERIES_CODE"].notna().all()
    assert len(download) == len(preview) - int(coordinate_masked(preview).sum())


def test_quarantine_query_does_not_require_current_rows():
    sql, _ = build_search_sql(SeriesFilter.build(lifecycle="quarantine"))
    assert "WHERE BATCH_STATUS = 'QUARANTINE'" in sql
    assert "FAILED_RULE_ID" in sql
    assert "SUBMISSION_ID" in sql