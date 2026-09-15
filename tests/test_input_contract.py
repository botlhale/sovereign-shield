from decimal import Decimal

import pandas as pd
import pytest

from sdmx_rule_validator import SDMxRuleValidator


def submission(**overrides):
    row = {
        "TIME_SERIES_CODE": "Q.S.C.A.USD.F.5J.A.CA.B.DE",
        "DATE": "2026-Q1", "AGG_CODE": "LBSR", "OBS_VALUE": "1234567.891",
        "OBS_STATUS": "A", "OBS_CONF": "F",
    }
    row.update(overrides)
    return pd.DataFrame([row])


@pytest.mark.parametrize("overrides, message", [
    ({"TIME_SERIES_CODE": "Q.S.C.A.USD.F.5J.A.INVALID.B.DE"}, "L_REP_CTY"),
    ({"OBS_CONF": "UNRECOGNIZED"}, "OBS_CONF"),
    ({"OBS_CONF": None}, "OBS_CONF"),
    ({"OBS_STATUS": "INVALID"}, "OBS_STATUS"),
    ({"DATE": "2026-Q5"}, "DATE"),
    ({"OBS_VALUE": "NaN"}, "OBS_VALUE"),
    ({"L_POS_TYPE": "C"}, "Unknown"),
])
def test_invalid_submission_is_rejected_before_arithmetic(overrides, message):
    with pytest.raises(ValueError, match=message):
        SDMxRuleValidator().validate(submission(**overrides))


def test_duplicate_observation_in_one_submission_is_rejected():
    frame = pd.concat([submission(), submission()], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate"):
        SDMxRuleValidator().validate(frame)


def test_values_are_decimal_at_three_places():
    result = SDMxRuleValidator().validate(submission(OBS_VALUE="1234567.8915"))
    assert isinstance(result.iloc[0]["OBS_VALUE"], Decimal)
    assert str(result.iloc[0]["OBS_VALUE"]) == "1234567.892"


def test_key_normalization_preserves_the_security_anchor():
    result = SDMxRuleValidator().validate(submission(
        TIME_SERIES_CODE="q.s.c.a.usd.f.5j.a.ca.b.de", OBS_CONF=" f "
    ))
    assert result.iloc[0]["TIME_SERIES_CODE"] == "Q.S.C.A.USD.F.5J.A.CA.B.DE"
    assert result.iloc[0]["OBS_CONF"] == "F"


@pytest.mark.parametrize("value", ["1234567.891", "-1234567.891", "123456789012345678901234567890.123"])
def test_all_wire_formats_preserve_three_decimal_values(value):
    import csv
    import io
    import simplejson
    import sdmx_ml_exporter as exporter
    from pysdmx.io import read_sdmx

    frame = submission(OBS_VALUE=value)
    xml = exporter.to_sdmx_ml_3_0(frame, validate=True)
    parsed = read_sdmx(xml, validate=True).get_datasets()[0].data
    assert Decimal(parsed.iloc[0]["OBS_VALUE"]) == Decimal(value)
    record = next(csv.DictReader(io.StringIO(exporter.to_sdmx_csv_2_0_0(frame))))
    assert record["OBS_VALUE"] == value
    assert record["DECIMALS"] == "3"
    message = simplejson.loads(exporter.to_sdmx_json_2_0_0(frame), use_decimal=True)
    cell = next(iter(message["data"]["dataSets"][0]["series"].values()))["observations"]["0"]
    assert cell[0] == Decimal(value)


@pytest.mark.parametrize("wire_format", ["sdmx-ml", "sdmx-json", "sdmx-csv"])
def test_standard_formats_refuse_duplicate_lifecycle_keys(wire_format):
    import sdmx_ml_exporter as exporter

    frame = pd.concat([submission(), submission()], ignore_index=True)
    with pytest.raises(exporter.SdmxSerializationError, match="Duplicate"):
        exporter.serialize(frame, wire_format)
    frame["BATCH_STATUS"] = ["PUBLISHED", "QUARANTINE"]
    with pytest.raises(exporter.SdmxSerializationError, match="published"):
        exporter.serialize(frame, wire_format)


@pytest.mark.parametrize("cycle, verdict", [("baseline", "PUBLISHED"), ("revision", "QUARANTINE")])
def test_synthetic_messages_pass_the_full_input_contract(tmp_path, cycle, verdict):
    from generate_sovereign_submissions import aggregate_micro_to_macro, generate_micro_transactions, generate_sdmx_ml

    validator = SDMxRuleValidator()
    count = 0
    for country, micro in generate_micro_transactions(cycle).items():
        macro = aggregate_micro_to_macro(micro)
        path = generate_sdmx_ml(macro, country, output_dir=str(tmp_path))
        loaded = validator.load_submission(path)
        result = validator.validate(loaded)
        assert result["BATCH_STATUS"].eq(verdict).all()
        assert result.attrs["SUBMISSION_ID"].startswith(f"SUBMITTER_{country.upper()}:")
        count += len(result)
    assert count == 22


def test_wire_message_rejects_a_sender_country_mismatch(tmp_path):
    import sdmx_ml_exporter as exporter

    path = tmp_path / "submission.xml"
    path.write_text(exporter.to_sdmx_ml_3_0(submission(), sender_id="SUBMITTER_US"), encoding="utf-8")
    with pytest.raises(ValueError, match="Sender-country mismatch"):
        SDMxRuleValidator().load_submission(str(path))


@pytest.mark.parametrize("empty", [False, True])
def test_json_matches_the_official_versioned_schema(empty):
    import hashlib
    import json
    from pathlib import Path
    from jsonschema import Draft7Validator
    import lbs_contract
    import sdmx_ml_exporter as exporter

    path = Path(lbs_contract.__file__).parent / "reference_data" / "sdmx_json_2_0.schema.json"
    payload = path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lbs_contract.structure_contract()["json_schema_sha256"]
    schema = json.loads(payload)
    Draft7Validator.check_schema(schema)
    frame = submission().iloc[:0] if empty else submission()
    if empty:
        with pytest.raises(exporter.SdmxSerializationError, match="No observations"):
            exporter.to_sdmx_json_2_0_0(frame)
        return
    Draft7Validator(schema).validate(json.loads(exporter.to_sdmx_json_2_0_0(frame)))