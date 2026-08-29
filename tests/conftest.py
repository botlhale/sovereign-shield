"""Shared fixtures for the SovereignShield test suite.

Tests run **offline by default**. That is a design constraint rather than a
convenience: the whole point of the contractor delivery pattern is that the
security model can be verified without holding credentials for the system it
protects. A suite that only runs against a live workspace would be unrunnable by
the very person it exists to constrain.

The persona assertions therefore execute against ``LocalDeltaBackend``, the
pandas mirror of the Unity Catalog row filter and column mask. The identical
assertions can be re-run against real Unity Catalog with::

    pytest --live

which requires DATABRICKS_SERVER_HOSTNAME plus a per-persona token. The mirror
is a development convenience whose correctness is verified against the real
thing; when it drifts from the metastore, the live run fails.
"""

from __future__ import annotations

import os
import sys
from typing import Dict

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

#: Personas exactly as named in unity_catalog_triple_lock.sql. Any drift between
#: this mapping and the DDL is a defect the live run will surface.
PERSONA_GROUPS: Dict[str, frozenset] = {
    "public": frozenset({"sg-sovereignshield-public"}),
    "researcher": frozenset({"sg-sovereignshield-researchers"}),
    "submitter_ca": frozenset({"sg-sovereignshield-submitter-ca"}),
    "submitter_us": frozenset({"sg-sovereignshield-submitter-us"}),
    "admin": frozenset({"sg-sovereignshield-admin"}),
    "unaffiliated": frozenset(),
}


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run persona assertions against real Unity Catalog instead of the local mirror.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "live: requires a reachable Databricks workspace")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="needs --live and a reachable workspace")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def repo_root() -> str:
    return REPO_ROOT


@pytest.fixture(scope="session")
def corpus() -> pd.DataFrame:
    """The Minimal Viable Synthetic Dataset, in memory.

    Deliberately hand-built rather than loaded from ``data/``: a test that
    depends on pipeline output cannot fail independently of the pipeline, and
    every row class required by ``mvsd_specification.md`` §5 has to be present
    for the assertions below to mean anything.

    Coverage encoded here:
      * three jurisdictions (CA, US, GB) so isolation is distinguishable
      * F and C/N rows in **more than one** jurisdiction, which is what catches
        a mask that checks group membership without checking segment 9
      * a quarantined batch owned by CA
      * a superseded (IS_CURRENT = false) published row for SCD2 history
    """
    def key(rep_cty: str, position: str = "C", denom: str = "USD", sector: str = "A") -> str:
        return f"Q.S.{position}.A.{denom}.F.5J.A.{rep_cty}.{sector}.5J"

    rows = [
        # (key, date, value, obs_conf, batch_status, is_current)
        (key("CA"), "2026-Q1", 1000.0, "F", "PUBLISHED", True),
        (key("CA", denom="CAD"), "2026-Q1", 250.0, "C", "PUBLISHED", True),
        (key("CA", position="L"), "2026-Q1", -400.0, "N", "PUBLISHED", True),
        (key("CA", sector="B"), "2026-Q1", 99.0, "F", "QUARANTINE", False),
        (key("CA"), "2025-Q4", 900.0, "F", "PUBLISHED", False),
        (key("US"), "2026-Q1", 2000.0, "F", "PUBLISHED", True),
        (key("US", denom="USD", sector="B"), "2026-Q1", 750.0, "C", "PUBLISHED", True),
        (key("US", position="L"), "2026-Q1", -120.0, "N", "PUBLISHED", True),
        (key("GB"), "2026-Q1", 1500.0, "F", "PUBLISHED", True),
        (key("GB", denom="GBP"), "2026-Q1", 333.0, "C", "PUBLISHED", True),
    ]

    return pd.DataFrame(
        [
            {
                "TIME_SERIES_CODE": k,
                "DATE": d,
                "IBS_AGG": "LBSR",
                "OBS_VALUE": v,
                "OBS_STATUS": "A",
                "OBS_CONF": c,
                "QUALITY_STATUS": "FAIL" if b == "QUARANTINE" else "PASS",
                "BATCH_STATUS": b,
                "IS_CURRENT": cur,
            }
            for k, d, v, c, b, cur in rows
        ]
    )


@pytest.fixture(scope="session")
def visible_rows():
    """Returns ``(persona_name, corpus) -> DataFrame`` as that persona sees it."""
    from uc_query import LocalDeltaBackend, Principal

    def _visible(persona: str, frame: pd.DataFrame) -> pd.DataFrame:
        principal = Principal(
            display_name=persona,
            groups=PERSONA_GROUPS[persona],
            authenticated=persona != "public",
        )
        return LocalDeltaBackend._apply_persona(frame, principal)

    return _visible


def reporting_country(series_key: str) -> str:
    """Segment 9 of the composite key - the sovereignty anchor."""
    return series_key.split(".")[8]
