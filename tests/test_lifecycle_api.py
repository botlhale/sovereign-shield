import csv
import io
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api_gateway as api
from uc_query import LocalDeltaBackend, Principal, SeriesFilter, build_search_sql


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


def test_empty_standard_export_is_no_content(client):
    assert client.get("/api/v1/export/sdmx-json?reporting_country=ZZ").status_code == 204


def test_quarantine_query_does_not_require_current_rows():
    sql, _ = build_search_sql(SeriesFilter.build(lifecycle="quarantine"))
    assert "WHERE BATCH_STATUS = 'QUARANTINE'" in sql
    assert "FAILED_RULE_ID" in sql
    assert "SUBMISSION_ID" in sql