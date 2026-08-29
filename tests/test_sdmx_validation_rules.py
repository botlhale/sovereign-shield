"""Validation-rule assertions: non-compliant records must never reach Silver.

Covers the two enforcement points a malformed submission has to pass:

* ``SDMxRuleValidator`` - arithmetic reconciliation against the BIS rulebook,
  with an atomic per-country-quarter verdict
* ``sdmx_ml_exporter`` - structural validity of anything serialised outward

All offline. The rulebook is a local workbook and the exporter falls back to a
local writer when the BIS registry is unreachable.
"""

from __future__ import annotations

import pandas as pd
import pytest

import sdmx_ml_exporter as sdmx
from sdmx_rule_validator import FALLBACK_DSD_DIMENSIONS, SDMxRuleValidator


@pytest.fixture(scope="module")
def validator() -> SDMxRuleValidator:
    return SDMxRuleValidator()


def _macro_frame(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "TIME_SERIES_CODE": k,
                "DATE": "2026-Q1",
                "IBS_AGG": "LBSR",
                "OBS_VALUE": v,
                "OBS_STATUS": "A",
                "OBS_CONF": "F",
            }
            for k, v in rows
        ]
    )


# ---------------------------------------------------------------------------
# Structural conformance
# ---------------------------------------------------------------------------


def test_dimension_order_is_the_eleven_lbs_dimensions():
    """Segment order is not cosmetic - position 9 is the sovereignty anchor."""
    assert FALLBACK_DSD_DIMENSIONS == [
        "FREQ",
        "L_MEASURE",
        "L_POSITION",
        "L_INSTR",
        "L_DENOM",
        "L_CURR_TYPE",
        "L_PARENT_CTY",
        "L_REP_BANK_TYPE",
        "L_REP_CTY",
        "L_CP_SECTOR",
        "L_CP_COUNTRY",
    ]
    assert FALLBACK_DSD_DIMENSIONS.index("L_REP_CTY") == 8


def test_exporter_dimension_set_matches_the_validator():
    """Two modules, one structure. Drift here silently misaligns every export."""
    assert sdmx.SDMX_DIMENSIONS == FALLBACK_DSD_DIMENSIONS
    assert sdmx.REP_CTY_SEGMENT == 9


@pytest.mark.parametrize(
    "bad_key",
    [
        "Q.S.C.A.USD",                          # too few segments
        "Q.S.C.A.USD.F.5J.A.CA.A.5J.EXTRA",     # too many
        "",                                     # empty
    ],
)
def test_malformed_key_is_rejected_before_serialization(bad_key):
    """A ragged key must raise, not be padded.

    ``str.split(expand=True)`` pads short keys with NaN and sizes itself by the
    longest key present, so a single malformed row would silently shift every
    subsequent dimension and misalign the whole batch instead of erroring.
    """
    frame = _macro_frame([(bad_key, 100.0)])

    with pytest.raises(sdmx.SdmxSerializationError):
        sdmx.explode_series_keys(frame)


def test_wellformed_key_parses_to_named_dimensions():
    parsed = sdmx.parse_series_key("Q.S.C.A.USD.F.5J.A.CA.A.5J")

    assert parsed["L_REP_CTY"] == "CA"
    assert parsed["L_DENOM"] == "USD"
    assert len(parsed) == 11


# ---------------------------------------------------------------------------
# Validator verdicts
# ---------------------------------------------------------------------------


def test_empty_batch_is_a_valid_state_not_an_error(validator):
    """A non-reporting quarter is legitimate and must not raise."""
    result = validator.validate(_macro_frame([]))

    assert result.empty
    for column in ("QUALITY_STATUS", "BATCH_STATUS", "FAILED_RULE_ID"):
        assert column in result.columns


def test_validator_rejects_ragged_keys(validator):
    """Arity is checked per row, before any rule is evaluated."""
    frame = _macro_frame(
        [("Q.S.C.A.USD.F.5J.A.CA.A.5J", 100.0), ("Q.S.C.A.USD", 50.0)]
    )

    with pytest.raises(Exception):
        validator.validate(frame)


def test_clean_batch_publishes(validator):
    """A realistic batch with no aggregate placeholders has nothing to reconcile."""
    frame = _macro_frame(
        [
            ("Q.S.C.A.USD.F.5J.A.CA.B.DE", 100.0),
            ("Q.S.C.A.CAD.D.5J.A.CA.B.FR", 250.0),
        ]
    )
    result = validator.validate(frame)

    assert (result["QUALITY_STATUS"] == "PASS").all()
    assert (result["BATCH_STATUS"] == "PUBLISHED").all()
    assert result["FAILED_RULE_ID"].isna().all()


def test_broken_reconciliation_quarantines_the_whole_country_quarter(validator):
    """Failure is atomic per (L_REP_CTY, DATE).

    Partial publication is incoherent, not merely undesirable: the aggregates
    that reconcile depend on the components that did not, so publishing the
    passing subset emits an internally contradictory dataset.

    The group below pins every dimension except ``L_CP_SECTOR`` and uses the BIS
    aggregate code ``A`` against components ``B`` and ``N`` - the shape
    ``LBS_CC:04`` reconciles. The aggregate is deliberately wrong.
    """
    context = "Q.S.C.A.TO1.A.5J.A.CA.{sector}.5J"
    frame = _macro_frame(
        [
            (context.format(sector="A"), 1000.0),  # claims to be B + N
            (context.format(sector="B"), 300.0),
            (context.format(sector="N"), 200.0),   # 300 + 200 != 1000
        ]
    )
    result = validator.validate(frame)

    assert (result["QUALITY_STATUS"] == "FAIL").all(), "verdict must cover every row"
    assert (result["BATCH_STATUS"] == "QUARANTINE").all()
    assert result["FAILED_RULE_ID"].notna().all()


def test_quarantine_does_not_cross_jurisdictions(validator):
    """One sovereign's break must never block another's publication."""
    ca = "Q.S.C.A.TO1.A.5J.A.CA.{sector}.5J"
    frame = _macro_frame(
        [
            (ca.format(sector="A"), 1000.0),
            (ca.format(sector="B"), 300.0),
            (ca.format(sector="N"), 200.0),
            ("Q.S.C.A.USD.F.5J.A.US.B.DE", 500.0),
        ]
    )
    result = validator.validate(frame)

    verdict = dict(
        zip(
            result["TIME_SERIES_CODE"].str.split(".").str[8],
            result["BATCH_STATUS"],
        )
    )
    assert verdict["CA"] == "QUARANTINE"
    assert verdict["US"] == "PUBLISHED"


def test_signed_values_are_not_failures(validator):
    """LBS positions are legitimately negative - direction, not defect."""
    frame = _macro_frame([("Q.S.L.A.USD.F.5J.A.CA.B.DE", -4200.0)])
    result = validator.validate(frame)

    assert (result["BATCH_STATUS"] == "PUBLISHED").all()


def test_rule_codes_match_the_published_workbook(validator):
    """Codes are read from the workbook, never assumed.

    The source formatting is genuinely inconsistent - ``LBS_CC01`` has no colon
    while ``LBS_CC:04`` does. Normalising it would silently drop rules.
    """
    codes = {rule.check_no for rule in validator.rules}

    assert codes, "no rules parsed - check docs/reference_standards/checks_lbs.xls"
    assert all(code.startswith("LBS_CC") for code in codes)


# ---------------------------------------------------------------------------
# Serialization conformance
# ---------------------------------------------------------------------------


def test_generic_data_format_is_rejected():
    """SDMX 3.0.0 removed GenericData; only StructureSpecificData remains."""
    frame = _macro_frame([("Q.S.C.A.USD.F.5J.A.CA.A.5J", 100.0)])

    with pytest.raises(sdmx.SdmxSerializationError):
        sdmx.to_sdmx_ml_3_0(frame, output_type="GenericData")


def test_masked_observation_serializes_as_absent_not_zero():
    """A redacted value and a zero mean entirely different things in SDMx.

    Conflating them would turn a confidentiality control into a data-quality
    defect - and zero-valued observations are not reported at all under SDMx
    convention.
    """
    frame = _macro_frame([("Q.S.C.A.USD.F.5J.A.CA.A.5J", None)])

    xml = sdmx.to_sdmx_ml_3_0(frame, validate=True)
    csv = sdmx.to_sdmx_csv_2_0_0(frame)

    assert "OBS_VALUE=\"0\"" not in xml
    assert 'OBS_VALUE="' not in xml, "an absent measure must omit the attribute entirely"
    assert ",0," not in csv


def test_sdmx_csv_carries_the_structure_reference():
    """SDMX-CSV 2.0.0 rows are self-describing rather than order-dependent."""
    frame = _macro_frame([("Q.S.C.A.USD.F.5J.A.CA.A.5J", 100.0)])

    csv = sdmx.to_sdmx_csv_2_0_0(frame)
    header, first = csv.splitlines()[0], csv.splitlines()[1]

    assert header.startswith("STRUCTURE,STRUCTURE_ID,ACTION,")
    assert first.startswith("dataflow,BIS:WS_LBS_D_PUB(1.0),")


def test_serialized_xml_round_trips():
    """Validation happens here, not at the receiving institution."""
    frame = _macro_frame(
        [
            ("Q.S.C.A.USD.F.5J.A.CA.A.5J", 100.0),
            ("Q.S.C.A.USD.F.5J.A.US.A.5J", 200.0),
        ]
    )

    xml = sdmx.to_sdmx_ml_3_0(frame, validate=True)

    assert "StructureSpecificData" in xml
    assert "GenericData" not in xml
    assert sdmx.structure_urn() in xml, "the message must name the dataflow it reports against"


def test_observations_are_grouped_into_series():
    """A time-series dataflow nests <Obs> under <Series>.

    pysdmx defaults to ``AllDimensions``, which emits one flat ``<Obs>`` per row
    and no ``<Series>`` at all. Both writers are pinned to ``TIME_PERIOD`` so the
    shape does not depend on which one served the request.
    """
    frame = _macro_frame(
        [
            ("Q.S.C.A.USD.F.5J.A.CA.A.5J", 100.0),
            ("Q.S.C.A.USD.F.5J.A.CA.A.5J", 150.0),
        ]
    )

    xml = sdmx.to_sdmx_ml_3_0(frame, validate=True)

    assert "<Series" in xml
    assert 'dimensionAtObservation="TIME_PERIOD"' in xml
