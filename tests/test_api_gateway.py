"""API response-shape regression tests."""

import math
from io import BytesIO
from unittest.mock import patch

import pandas as pd
from starlette.requests import Request

from api_gateway import _easy_auth_access_token, _easy_auth_identities, _json_records


def test_masked_numeric_values_are_json_nulls():
    records = _json_records(pd.DataFrame({"OBS_VALUE": [100.0, float("nan")]}))

    assert records == [{"OBS_VALUE": 100.0}, {"OBS_VALUE": None}]
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