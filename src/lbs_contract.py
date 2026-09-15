"""Offline, version-pinned BIS LBS domain checks, separate from format validation."""

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from decimal_measures import decimal_value

MACRO_COLUMNS = ["TIME_SERIES_CODE", "DATE", "AGG_CODE", "OBS_VALUE", "OBS_STATUS", "OBS_CONF"]
SERIES_ATTRIBUTES = ["TIME_FORMAT", "AVAILABILITY", "COLLECTION"]
DATASET_ATTRIBUTES = ["DECIMALS", "UNIT_MEASURE", "UNIT_MULT"]
DATASET_PROFILE = {"DECIMALS": "3", "UNIT_MEASURE": "USD", "UNIT_MULT": "6"}


@lru_cache(maxsize=1)
def structure_contract():
    path = Path(__file__).parent / "reference_data" / "lbs_structure.json"
    with path.open(encoding="utf-8") as source:
        contract = json.load(source)
    if contract["structure"] != "BIS:BIS_LBS(1.0)":
        raise ValueError("The pinned structure must be BIS:BIS_LBS(1.0).")
    return contract


def check_component_codes(frame, *, require_all=True):
    contract = structure_contract()
    unknown = set(frame.columns) - set(contract["components"])
    if unknown:
        raise ValueError(f"Unknown DSD component(s): {', '.join(sorted(unknown))}.")
    result = frame.copy()
    for name, spec in contract["components"].items():
        if name not in result:
            if spec["required"] and (require_all or spec["role"] != "Attribute" or name == "OBS_STATUS"):
                raise ValueError(f"Missing required DSD component: {name}.")
            continue
        codes = spec["codelist"]
        if codes:
            result[name] = result[name].astype("string").str.strip().str.upper()
            invalid = ~result[name].isin(contract["codelists"][codes])
            if not spec["required"] and name not in ("OBS_CONF", "OBS_STATUS"):
                invalid &= result[name].notna()
            if invalid.any():
                raise ValueError(f"Invalid {name} code: {result.loc[invalid, name].iloc[0]!r} ({codes}).")
    return result


def normalize_macro(frame, dimensions):
    missing = set(MACRO_COLUMNS) - set(frame.columns)
    unknown = set(frame.columns) - set(MACRO_COLUMNS) - {"MAX_BANK_SHARE"}
    if missing:
        raise ValueError(f"Missing component(s): {', '.join(sorted(missing))}.")
    if unknown:
        raise ValueError(f"Unknown or unsupported component(s): {', '.join(sorted(unknown))}.")
    result = frame.copy()
    keys = result["TIME_SERIES_CODE"].astype("string")
    invalid = keys.isna() | (keys.str.count(r"\.") + 1 != len(dimensions))
    if invalid.any():
        raise ValueError(f"TIME_SERIES_CODE must have {len(dimensions)} segments.")
    parsed = keys.str.split(".", expand=True)
    parsed.columns = dimensions
    parsed["TIME_PERIOD"] = result["DATE"]
    for name in ("OBS_STATUS", "OBS_CONF", "OBS_VALUE"):
        parsed[name] = result[name]
    parsed = check_component_codes(parsed, require_all=False)
    result["TIME_SERIES_CODE"] = parsed[dimensions].agg(".".join, axis=1)
    for name in ("OBS_STATUS", "OBS_CONF"):
        result[name] = parsed[name]
    result["DATE"] = result["DATE"].astype("string").str.strip().str.upper()
    patterns = {"A": r"\d{4}", "S": r"\d{4}-S[12]", "Q": r"\d{4}-Q[1-4]", "M": r"\d{4}-(0[1-9]|1[0-2])"}
    for frequency, period in zip(parsed["FREQ"], result["DATE"]):
        if frequency not in patterns or pd.isna(period) or not re.fullmatch(patterns[frequency], period):
            raise ValueError(f"DATE {period!r} is unsupported or invalid for FREQ {frequency!r}.")
    if not result["AGG_CODE"].eq("LBSR").all():
        raise ValueError("Only AGG_CODE LBSR is configured for this BIS LBS contract.")
    result["OBS_VALUE"] = result["OBS_VALUE"].map(decimal_value)
    if result.duplicated(["TIME_SERIES_CODE", "DATE", "AGG_CODE"]).any():
        raise ValueError("Duplicate observation key in a single submission.")
    return result


def with_message_profile(frame):
    result = frame.copy()
    result["TIME_FORMAT"] = result["FREQ"].map({"A": "P1Y", "S": "P6M", "Q": "P3M", "M": "P1M"})
    result["AVAILABILITY"] = "A"
    result["COLLECTION"] = "E"
    for name, value in DATASET_PROFILE.items():
        result[name] = value
    return check_component_codes(result)


@lru_cache(maxsize=1)
def pinned_components():
    from pysdmx.model import DataType
    from pysdmx.model.concept import Concept
    from pysdmx.model.dataflow import Component, Components, Role

    roles = {str(role): role for role in Role}
    types = {str(dtype): dtype for dtype in DataType}
    return Components([Component(
        id=name, required=spec["required"], role=roles[spec["role"]],
        concept=Concept(id=name), local_dtype=types[spec["type"]],
        attachment_level=spec["attachment_level"],
    ) for name, spec in structure_contract()["components"].items()])