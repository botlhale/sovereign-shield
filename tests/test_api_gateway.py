"""API response-shape regression tests."""

import math
from io import BytesIO
from unittest.mock import patch

import pandas as pd
import pytest
from starlette.requests import Request

from api_gateway import _easy_auth_access_token, _easy_auth_identities, _extract_token, _json_records, export_sdmx_ml
from uc_query import Principal, SeriesFilter


@pytest.mark.parametrize(
    "jurisdiction, label",
    [
        ("ca", "Canadian Regional Submitter (CA)"),
        ("us", "US Regional Submitter (US)"),
    ],
)
def test_submitter_label_and_export_sender_are_jurisdiction_based(jurisdiction, label):
    principal = Principal(
        display_name=label,
        groups=frozenset({f"sg-sovereignshield-submitter-{jurisdiction}"}),
        authenticated=True,
    )
    series_filter = SeriesFilter(limit=10)

    assert principal.access_label == label
    with patch("api_gateway._export") as serialize_export:
        export_sdmx_ml(principal=principal, series_filter=series_filter, limit=10)

    serialize_export.assert_called_once_with(
        "sdmx-ml",
        series_filter,
        principal,
        sender_id=f"SUBMITTER_{jurisdiction.upper()}",
        sender_name=label,
        validate=True,
    )


def test_masked_numeric_values_are_json_nulls():
    records = _json_records(pd.DataFrame({"OBS_VALUE": [100.0, float("nan")]}))

    assert records == [{"OBS_VALUE": "100.000"}, {"OBS_VALUE": None}]
    assert not any(math.isnan(value) for record in records for value in record.values() if isinstance(value, float))


def test_easy_auth_access_token_is_read_from_token_store(monkeypatch):
    request = Request({
        "type": "http",
        "scheme": "https",
        "server": ("portal.example", 443),
        "path": "/api/v1/whoami",
        "headers": [(b"cookie", b"AppServiceAuthSession=session")],
    })
    monkeypatch.setenv("SOVEREIGNSHIELD_EXTERNAL_URL", "https://portal.example")
    response = BytesIO(b'[{"access_token":"caller-token"}]')
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: None

    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        assert _easy_auth_access_token(request) == "caller-token"

    assert urlopen.call_args.args[0].full_url == "https://portal.example/.auth/me"


def test_easy_auth_identities_never_return_non_object_entries(monkeypatch):
    request = Request({
        "type": "http",
        "scheme": "https",
        "server": ("portal.example", 443),
        "path": "/api/v1/auth-diagnostics",
        "headers": [(b"cookie", b"AppServiceAuthSession=session")],
    })
    monkeypatch.setenv("SOVEREIGNSHIELD_EXTERNAL_URL", "https://portal.example")
    response = BytesIO(b'[{"id_token":"present"},null,"invalid"]')
    response.__enter__ = lambda: response
    response.__exit__ = lambda *args: None

    with patch("urllib.request.urlopen", return_value=response):
        assert _easy_auth_identities(request) == [{"id_token": "present"}]


def test_browser_bearer_token_precedes_server_side_easy_auth_lookup():
    request = Request({
        "type": "http",
        "scheme": "https",
        "server": ("portal.example", 443),
        "path": "/api/v1/whoami",
        "headers": [
            (b"authorization", b"Bearer browser-token"),
            (b"x-ms-client-principal", b"trusted-principal"),
        ],
    })

    with patch("api_gateway._easy_auth_access_token") as token_lookup:
        assert _extract_token(request) == "browser-token"

    token_lookup.assert_not_called()


def test_portal_uses_easy_auth_token_for_reads_and_exports(repo_root):
    portal = open(repo_root + "/src/templates/portal.html", encoding="utf-8").read()

    assert 'fetch("/.auth/me", { credentials: "same-origin" })' in portal
    assert 'Authorization: "Bearer " + easyAuthAccessToken' in portal
    assert 'authenticatedFetch("/api/v1/whoami")' in portal
    assert 'authenticatedFetch("/api/v1/facets")' in portal
    assert 'authenticatedFetch("/api/v1/search?" + params.toString())' in portal
    assert "const response = await authenticatedFetch(link.href);" in portal


def test_portal_uses_compact_cascading_filters(repo_root):
    from portal_ui import STATISTIC_CATALOG

    portal = open(repo_root + "/src/templates/portal.html", encoding="utf-8").read()

    assert set(STATISTIC_CATALOG) == {"IBS"}
    assert [item["code"] for item in STATISTIC_CATALOG["IBS"]["aggregations"]] == [
        "LBSR", "LBSN", "CBSI", "CBSG"
    ]
    assert "select multiple" not in portal
    assert 'id="apply"' not in portal
    assert 'id="statistic-type"' in portal
    assert 'id="aggregation"' in portal
    assert 'id="dimension-filters"' in portal
    assert 'data-filter-menu="{{ name }}"' in portal
    assert 'input.type = "checkbox"' in portal
    assert 'id="reference-period"' in portal
    assert "payload.reference_periods" in portal
    assert "scheduleSearch();" in portal
    assert "const sequence = ++searchSequence;" in portal


def test_portal_keeps_results_and_exports_in_one_desktop_workspace(repo_root):
    portal = open(repo_root + "/src/templates/portal.html", encoding="utf-8").read()

    assert ".portal-workspace { min-height: 0; flex: 1; width: 100%; }" in portal
    assert 'class="min-h-0 flex-1 overflow-auto"' in portal
    assert "sticky top-0" in portal
    assert 'id="export-sdmx-ml"' in portal


def test_portal_exports_inherit_the_previewed_quarantine_scope(repo_root):
    """An administrator's download must match what the preview shows.

    Export links are built from ``currentParams()``. While the quarantine flag
    was appended separately inside ``runSearch``, every export silently returned
    published rows only, however the checkbox was set.
    """
    portal = open(repo_root + "/src/templates/portal.html", encoding="utf-8").read()

    params_body = portal.split("function currentParams()", 1)[1].split("function scheduleSearch", 1)[0]

    assert 'params.append("lifecycle",' in params_body
    assert '"/api/v1/export/audit-csv"' in portal
    assert 'setAttribute("aria-disabled"' in portal
    assert "cdn.tailwindcss.com" not in portal
    assert "Number(value)" not in portal