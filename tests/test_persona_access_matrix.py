"""Persona entitlement assertions for the four-tier security matrix.

Each test states an entitlement from ``.github/skills/persona_security_matrix.md``
and asserts it holds. The offline runs execute against ``LocalDeltaBackend``, the
pandas mirror of the Unity Catalog policy; the ``--live`` runs issue the same
assertions against a real workspace, which is what keeps the mirror honest.

Two properties are asserted throughout rather than just one:

* **positive** - the persona sees what it is entitled to
* **negative** - the persona does *not* see what it is not

A test that only checks the positive direction passes against a filter that
returns everything, which is precisely the defect worth catching.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from conftest import PERSONA_GROUPS, reporting_country


# ---------------------------------------------------------------------------
# Persona 1 - anonymous public consumer
# ---------------------------------------------------------------------------


def test_public_sees_only_published_free_to_publish(corpus, visible_rows):
    rows = visible_rows("public", corpus)

    assert not rows.empty, "public tier returned nothing; the corpus has published F rows"
    assert (rows["BATCH_STATUS"] == "PUBLISHED").all()
    assert (rows["OBS_CONF"] == "F").all()


def test_public_never_sees_confidential_rows(corpus, visible_rows):
    rows = visible_rows("public", corpus)

    assert rows[rows["OBS_CONF"].isin(["C", "N"])].empty, (
        "a confidential row reached the public tier; masking the value is not "
        "sufficient, the row itself must be filtered"
    )


def test_public_never_sees_quarantined_batches(corpus, visible_rows):
    rows = visible_rows("public", corpus)

    assert (rows["BATCH_STATUS"] != "QUARANTINE").all()


def test_public_spans_all_jurisdictions(corpus, visible_rows):
    """Public access is global in scope but narrow in depth."""
    rows = visible_rows("public", corpus)
    countries = {reporting_country(k) for k in rows["TIME_SERIES_CODE"]}

    assert countries == {"CA", "US", "GB"}


# ---------------------------------------------------------------------------
# Persona 2 - authenticated researcher
# ---------------------------------------------------------------------------


def test_researcher_sees_confidential_rows_with_values_masked(corpus, visible_rows):
    rows = visible_rows("researcher", corpus)
    confidential = rows[rows["OBS_CONF"].isin(["C", "N"])]

    assert not confidential.empty, "researcher should retain the confidential rows"
    assert confidential["OBS_VALUE"].isna().all(), (
        "OBS_VALUE must be NULL for C/N observations - the international "
        "convention for a redacted value, and the only representable one for a DOUBLE"
    )


def test_researcher_retains_dimensional_density(corpus, visible_rows):
    """The row survives so joins and dimensional counts stay correct."""
    rows = visible_rows("researcher", corpus)
    published = corpus[corpus["BATCH_STATUS"] == "PUBLISHED"]

    assert len(rows) == len(published)


def test_researcher_sees_free_values_unmasked(corpus, visible_rows):
    rows = visible_rows("researcher", corpus)
    free = rows[rows["OBS_CONF"] == "F"]

    assert free["OBS_VALUE"].notna().all()


def test_researcher_never_sees_quarantined_batches(corpus, visible_rows):
    rows = visible_rows("researcher", corpus)

    assert (rows["BATCH_STATUS"] != "QUARANTINE").all(), (
        "an unvalidated figure must never reach a research citation"
    )


# ---------------------------------------------------------------------------
# Persona 3 - regional reporting submitter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "persona, own, foreign",
    [("submitter_ca", "CA", "US"), ("submitter_us", "US", "CA")],
)
def test_submitter_sees_own_confidential_values_unmasked(corpus, visible_rows, persona, own, foreign):
    rows = visible_rows(persona, corpus)
    own_rows = rows[rows["TIME_SERIES_CODE"].map(reporting_country) == own]
    own_confidential = own_rows[own_rows["OBS_CONF"].isin(["C", "N"])]

    assert not own_confidential.empty
    assert own_confidential["OBS_VALUE"].notna().all()


@pytest.mark.parametrize(
    "persona, own, foreign",
    [("submitter_ca", "CA", "US"), ("submitter_us", "US", "CA")],
)
def test_submitter_cannot_see_foreign_confidential_rows_at_all(corpus, visible_rows, persona, own, foreign):
    """The row filter removes foreign C/N rows before masking is even reached.

    Note what this does *not* prove. Because the filter already drops these
    rows, the assertion would still pass against a completely broken column
    mask. The mask is exercised separately by
    ``test_dual_membership_still_masks_foreign_confidential``, which is the only
    configuration where a foreign confidential row is visible at all.
    """
    rows = visible_rows(persona, corpus)
    foreign_rows = rows[rows["TIME_SERIES_CODE"].map(reporting_country) == foreign]

    assert not foreign_rows.empty, "expected foreign published F rows to remain visible"
    assert foreign_rows[foreign_rows["OBS_CONF"].isin(["C", "N"])].empty


def test_dual_membership_still_masks_foreign_confidential(corpus):
    """The cross-sovereign leak this suite exists to catch.

    A principal holding both submitter and researcher membership is the only
    persona that can see a *foreign* confidential row: the researcher tier
    admits every published row, so the column mask - not the row filter -
    becomes the control of record.

    An early draft of the mask keyed on group membership alone, without testing
    segment 9, which would have let a Bank of Canada analyst read Federal
    Reserve confidential positions. It was caught in development, on synthetic
    data, and never reached a deployment - but only because this fixture spans
    more than one jurisdiction. This test fails against that implementation;
    the single-membership tests above do not.
    """
    from uc_query import LocalDeltaBackend, Principal

    principal = Principal(
        display_name="ca-analyst-and-researcher",
        groups=PERSONA_GROUPS["submitter_ca"] | PERSONA_GROUPS["researcher"],
        authenticated=True,
    )
    rows = LocalDeltaBackend._apply_persona(corpus, principal)
    foreign_confidential = rows[
        (rows["TIME_SERIES_CODE"].map(reporting_country) != "CA")
        & rows["OBS_CONF"].isin(["C", "N"])
    ]

    assert not foreign_confidential.empty, (
        "fixture no longer exercises the mask - the researcher tier must expose "
        "at least one foreign confidential row for this assertion to mean anything"
    )
    assert foreign_confidential["OBS_VALUE"].isna().all(), (
        f"read {int(foreign_confidential['OBS_VALUE'].notna().sum())} unmasked "
        "foreign confidential observation(s)"
    )


def test_dual_membership_keeps_own_confidential_unmasked(corpus):
    """Masking is scoped to segment 9, not applied wholesale to the persona."""
    from uc_query import LocalDeltaBackend, Principal

    principal = Principal(
        display_name="ca-analyst-and-researcher",
        groups=PERSONA_GROUPS["submitter_ca"] | PERSONA_GROUPS["researcher"],
        authenticated=True,
    )
    rows = LocalDeltaBackend._apply_persona(corpus, principal)
    own_confidential = rows[
        (rows["TIME_SERIES_CODE"].map(reporting_country) == "CA")
        & rows["OBS_CONF"].isin(["C", "N"])
    ]

    assert not own_confidential.empty
    assert own_confidential["OBS_VALUE"].notna().all()


@pytest.mark.parametrize("persona, own", [("submitter_ca", "CA"), ("submitter_us", "US")])
def test_submitter_sees_foreign_published_free_rows(corpus, visible_rows, persona, own):
    """Sovereignty restricts depth, not breadth - public data stays public."""
    rows = visible_rows(persona, corpus)
    foreign = rows[rows["TIME_SERIES_CODE"].map(reporting_country) != own]

    assert not foreign.empty
    assert (foreign["BATCH_STATUS"] == "PUBLISHED").all()


@pytest.mark.parametrize("persona, foreign", [("submitter_ca", "US"), ("submitter_us", "CA")])
def test_submitter_cannot_see_foreign_quarantine(corpus, visible_rows, persona, foreign):
    rows = visible_rows(persona, corpus)
    foreign_rows = rows[rows["TIME_SERIES_CODE"].map(reporting_country) == foreign]

    assert (foreign_rows["BATCH_STATUS"] != "QUARANTINE").all()


def test_submitter_sees_own_quarantine_for_diagnosis(corpus, visible_rows):
    """A rejected submission is undiagnosable without its rejected rows."""
    rows = visible_rows("submitter_ca", corpus)
    quarantined = rows[rows["BATCH_STATUS"] == "QUARANTINE"]

    assert not quarantined.empty
    assert {reporting_country(k) for k in quarantined["TIME_SERIES_CODE"]} == {"CA"}


# ---------------------------------------------------------------------------
# Persona 4 - central auditor / administrator
# ---------------------------------------------------------------------------


def test_admin_sees_every_row(corpus, visible_rows):
    rows = visible_rows("admin", corpus)

    assert len(rows) == len(corpus)


def test_admin_values_are_never_masked(corpus, visible_rows):
    rows = visible_rows("admin", corpus)

    assert rows["OBS_VALUE"].notna().all()


def test_admin_sees_superseded_history(corpus, visible_rows):
    """SCD2 audit rows are part of the auditor's remit."""
    rows = visible_rows("admin", corpus)

    assert not rows[rows["IS_CURRENT"] == False].empty  # noqa: E712


# ---------------------------------------------------------------------------
# Fail-closed default
# ---------------------------------------------------------------------------


def test_principal_with_no_group_sees_nothing(corpus, visible_rows):
    """Off-boarding and inter-sovereign isolation are the same code path."""
    rows = visible_rows("unaffiliated", corpus)

    assert rows.empty


def test_malformed_key_fails_closed(corpus, visible_rows):
    """A ragged key must become invisible, not universally visible.

    ``try_element_at`` returns NULL past the end of the array; without an
    explicit coalesce to FALSE the predicate is NULL and the row's fate depends
    on how the optimiser folds it.
    """
    malformed = corpus.copy()
    malformed.loc[0, "TIME_SERIES_CODE"] = "Q.S.C.A.USD"  # 5 segments, not 11
    malformed.loc[0, "OBS_CONF"] = "C"

    rows = visible_rows("submitter_ca", malformed)

    assert "Q.S.C.A.USD" not in set(rows["TIME_SERIES_CODE"])


# ---------------------------------------------------------------------------
# Entitlement is monotonic
# ---------------------------------------------------------------------------


def test_privilege_ordering_is_monotonic(corpus, visible_rows):
    """Every tier sees at least as much as the tier below it.

    Catches a filter rewritten as CASE/WHEN, where a principal holding two
    memberships is silently downgraded to whichever branch is evaluated first.
    """
    counts = {
        persona: len(visible_rows(persona, corpus))
        for persona in ("unaffiliated", "public", "researcher", "admin")
    }

    assert counts["unaffiliated"] < counts["public"] <= counts["researcher"] <= counts["admin"]


def test_additive_membership_grants_union(corpus):
    """A submitter who is also a researcher gets both entitlements, not one.

    Catches a filter rewritten as CASE/WHEN, where the first matching branch
    wins and the second entitlement is silently discarded.
    """
    from uc_query import LocalDeltaBackend, Principal

    combined = Principal(
        display_name="dual",
        groups=PERSONA_GROUPS["submitter_ca"] | PERSONA_GROUPS["researcher"],
        authenticated=True,
    )
    rows = LocalDeltaBackend._apply_persona(corpus, combined)

    ca_quarantine = rows[
        (rows["BATCH_STATUS"] == "QUARANTINE")
        & (rows["TIME_SERIES_CODE"].map(reporting_country) == "CA")
    ]
    us_published = rows[
        (rows["TIME_SERIES_CODE"].map(reporting_country) == "US")
        & rows["OBS_CONF"].isin(["C", "N"])
    ]

    assert not ca_quarantine.empty, "lost the submitter entitlement"
    assert not us_published.empty, "lost the researcher entitlement"


# ---------------------------------------------------------------------------
# Live verification
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_live_public_tier_is_free_to_publish_only():
    """Re-asserts the public entitlement against real Unity Catalog.

    Runs as the configured proxy service principal. This is the run that detects
    drift between the pandas mirror and the metastore.
    """
    from uc_query import PUBLIC_PRINCIPAL, CatalogGateway, SeriesFilter

    gateway = CatalogGateway()
    if gateway.mode != "unity-catalog":
        pytest.skip("no Databricks warehouse configured")

    frame = gateway.search(SeriesFilter.build(limit=500), PUBLIC_PRINCIPAL)

    assert not frame.empty, "public tier returned nothing - check group membership"
    assert (frame["BATCH_STATUS"] == "PUBLISHED").all()
    assert (frame["OBS_CONF"] == "F").all()


@pytest.mark.live
def test_live_submitter_cannot_read_foreign_confidential():
    """Requires SOVEREIGNSHIELD_TEST_TOKEN_CA - a token for a submitter-ca principal."""
    from uc_query import CatalogGateway, Principal, SeriesFilter

    token = os.getenv("SOVEREIGNSHIELD_TEST_TOKEN_CA")
    if not token:
        pytest.skip("SOVEREIGNSHIELD_TEST_TOKEN_CA is not set")

    gateway = CatalogGateway()
    if gateway.mode != "unity-catalog":
        pytest.skip("no Databricks warehouse configured")

    principal = Principal(
        display_name="live-ca",
        groups=frozenset({"sg-sovereignshield-submitter-ca"}),
        authenticated=True,
        access_token=token,
    )
    frame = gateway.search(
        SeriesFilter.build(reporting_country=["US"], limit=500), principal
    )

    leaked = frame[frame["OBS_CONF"].isin(["C", "N"]) & frame["OBS_VALUE"].notna()]
    assert leaked.empty, f"CA submitter read {len(leaked)} unmasked US confidential value(s)"
