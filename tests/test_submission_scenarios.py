"""The reporting agents' scenarios must mean what their docstrings claim.

`generate_sovereign_submissions` asserts that its baseline reconciles against
every BIS consistency check and that each revision breaks a specific, named one.
Those are claims about a workbook the module never opens, so nothing in the
module can keep them true. This is where they are held to the rulebook.

Confidentiality and quality are checked separately on purpose. A dominant bank
makes an observation confidential; it does not make the submission wrong, and a
change that conflated the two would pass a test that only looked at one.

Offline apart from the DSD lookup, which falls back to the local dimension list.
"""

from __future__ import annotations

import pandas as pd
import pytest

from generate_sovereign_submissions import (
    DOMINANCE_THRESHOLD,
    SUBMISSION_CYCLES,
    aggregate_micro_to_macro,
    generate_micro_transactions,
)
from sdmx_rule_validator import SDMxRuleValidator


@pytest.fixture(scope="module")
def validator() -> SDMxRuleValidator:
    return SDMxRuleValidator()


def _submitted_macro(cycle: str) -> pd.DataFrame:
    """Every country's filing for one cycle, as the receiving hub would see it."""
    frames = [
        aggregate_micro_to_macro(df_micro, threshold=DOMINANCE_THRESHOLD)
        for df_micro in generate_micro_transactions(cycle=cycle).values()
    ]
    macro = pd.concat(frames, ignore_index=True)
    macro["OBS_STATUS"] = "A"
    return macro


def _by_country(result: pd.DataFrame) -> pd.Series:
    return result["TIME_SERIES_CODE"].str.split(".").str[8]


def test_cycles_are_declared_in_filing_order():
    assert SUBMISSION_CYCLES == ("baseline", "revision")


def test_baseline_reconciles_for_every_country(validator):
    """The baseline is the control. If it does not publish, the revision proves nothing."""
    result = validator.validate(_submitted_macro("baseline"))

    assert (result["BATCH_STATUS"] == "PUBLISHED").all()
    assert (result["QUALITY_STATUS"] == "PASS").all()
    assert result["FAILED_RULE_ID"].isna().all()


def test_every_country_is_quarantined_on_revision(validator):
    result = validator.validate(_submitted_macro("revision"))

    quarantined = set(_by_country(result)[result["BATCH_STATUS"] == "QUARANTINE"])
    assert quarantined == {"CA", "US", "GB"}


@pytest.mark.parametrize(
    "country, expected_rules",
    [
        ("CA", {"LBS_CC01"}),
        ("US", {"LBS_CC01"}),
        ("GB", {"LBS_CC02", "LBS_CC:04"}),
    ],
)
def test_revision_breaks_the_documented_checks(validator, country, expected_rules):
    """The rule codes in the scenario docstrings are read back off the workbook.

    Asserting the exact set, not merely a non-empty one: a scenario that drifted
    into breaking some other check would still quarantine, and would still look
    correct in the run log.
    """
    result = validator.validate(_submitted_macro("revision"))
    result = result[_by_country(result) == country]

    attributed = set(
        result.loc[result["FAILED_RULE_ID"].notna(), "FAILED_RULE_ID"]
    )
    assert attributed == expected_rules


def test_only_the_offending_observation_carries_the_rule(validator):
    """Quarantine is collective, attribution is not.

    Every row of a broken country-quarter is withheld, but naming the rule on all
    of them would point an investigator at series that reconcile perfectly.
    """
    result = validator.validate(_submitted_macro("revision"))
    accused = result["FAILED_RULE_ID"].notna()

    assert (result["BATCH_STATUS"] == "QUARANTINE").all()
    assert accused.sum() == 4, "one offending observation per documented break"
    assert accused.sum() < len(result), "attribution must be narrower than the verdict"


def test_dominance_restricts_publication_without_failing_validation(validator):
    """Confidentiality is the reporting country's call, quality is the hub's.

    ``BANK_US_1`` holds 70% of the US aggregate, so those observations are
    restricted. The submission is still arithmetically clean and must publish:
    withholding a value and rejecting a filing are different acts.
    """
    macro = _submitted_macro("baseline")
    us = macro[macro["TIME_SERIES_CODE"].str.split(".").str[8] == "US"]

    assert (us["OBS_CONF"] == "N").any(), "a dominated series must be restricted"

    result = validator.validate(macro)
    us_result = result[_by_country(result) == "US"]
    assert (us_result["BATCH_STATUS"] == "PUBLISHED").all()


def test_confidentiality_is_decided_before_the_hub_sees_it(validator):
    """The dominance verdict must not depend on the cycle's arithmetic."""
    restricted = {}
    for cycle in SUBMISSION_CYCLES:
        macro = _submitted_macro(cycle)
        country = macro["TIME_SERIES_CODE"].str.split(".").str[8]
        restricted[cycle] = country[macro["OBS_CONF"] == "N"].value_counts().to_dict()

    assert restricted["baseline"] == restricted["revision"]


def test_published_data_exercises_the_mask_in_both_directions():
    """The persona matrix is only meaningful if the mask has both kinds of row.

    All-restricted output would make a broken mask indistinguishable from a working
    one: every persona would see nothing either way. All-free output would never
    exercise the mask at all. The baseline must carry both, in more than one
    jurisdiction, or the Stage 6 verification proves nothing.
    """
    macro = _submitted_macro("baseline")
    country = macro["TIME_SERIES_CODE"].str.split(".").str[8]

    free = country[macro["OBS_CONF"] == "F"]
    restricted = country[macro["OBS_CONF"] == "N"]

    assert len(free) >= 10, "too few publishable series to demonstrate anything"
    assert free.nunique() >= 2, "publishable data must span more than one jurisdiction"
    assert len(restricted) >= 1, "nothing left for the mask to withhold"
