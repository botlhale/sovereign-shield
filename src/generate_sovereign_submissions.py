"""Sovereign-isolated synthetic micro-data generation and SDMx 3.0 XML submission.

This module models a "Sovereign Isolation" architecture in which each
reporting country's bank-level submissions live in their own micro-data
table (e.g. ``dbw_sovereignshield.sovereign_shield.lbs_micro_transactions_ca``,
``_us``, and ``_gb``), are aggregated locally into SDMx 3.0 macro time series,
and are serialized into official SDMx 3.0 XML (ML) submission files using the
live Data Structure Definition (DSD) fetched from the BIS REST API.

Three synthetic national scenarios are produced for pipeline testing:

* Canada (``CA``): a clean submission whose currency-type components
  (Domestic + Foreign + Unallocated) mathematically reconcile with the
  ``TO1.A`` aggregate per the ``LBS_CC01`` check in ``checks_lbs.xls``, and
  whose contributions are spread across three banks so none dominates.
* United States (``US``): a dirty submission whose components do NOT
  reconcile with the ``TO1.A`` aggregate (``LBS_CC01`` failure), and where a
  single bank contributes more than the dominance threshold of the
  aggregate, triggering restricted confidentiality.
* United Kingdom (``GB``): a mostly clean, reconciling submission with
  ``INVALID_RECORD_RATE`` (~15%) of its components deliberately corrupted
  (negative amounts, non-permitted sector/instrument pairings, and
  inconsistent bank-type/parent-country combinations) to exercise the
  quarantine path end-to-end.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pysdmx.io as sdmx_io
from pysdmx.io.format import Format
from pysdmx.io.pd import PandasDataset
from pysdmx.model import Organisation
from pysdmx.model.dataflow import DataStructureDefinition, Schema
from pysdmx.model.dataset import ActionType
from pysdmx.model.message import Header

# =====================================================================
# CONFIGURATION & CONSTANTS
# =====================================================================

#: The 11 BIS_LBS dimensions, in the exact order embedded in TIME_SERIES_CODE.
DSD_DIMENSIONS: List[str] = [
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

#: SDMx reporting quarter used for all synthetic submissions.
REPORTING_DATE: str = "2026-Q1"

#: Aggregation framework code (Locational Banking Statistics, restated basis).
IBS_AGG_CODE: str = "LBSR"

#: Default share of a single bank's contribution that triggers OBS_CONF = 'N'.
DOMINANCE_THRESHOLD: float = 0.60

#: Strict, required schema for each sovereign micro-data table.
MICRO_COLUMNS: List[str] = ["TIME_SERIES_CODE", "BANK_CODE", "DATE", "IBS_AGG", "OBS_VALUE"]

#: Live BIS REST endpoint exposing the BIS_LBS Data Structure Definition (DSD).
BIS_LBS_DSD_URL: str = "https://stats.bis.org/api/v1/datastructure/BIS/BIS_LBS/latest?references=all"

#: Directory where sovereign SDMx-ML submission files are written.
OUTPUT_DIR: str = "data"

#: Sovereign sender metadata (SDMx Header `sender`), keyed by lower-case country code.
SOVEREIGN_SENDERS: Dict[str, Organisation] = {
    "ca": Organisation(id="BOC", name="Bank of Canada"),
    "us": Organisation(id="FRB", name="Federal Reserve System"),
    "gb": Organisation(id="BOE", name="Bank of England"),
}

#: Data lifecycle states supported by `generate_sdmx_ml`, mapped to their SDMx `ActionType`.
SUBMISSION_ACTIONS: Dict[str, ActionType] = {
    "First Submission": ActionType.Information,
    "Revision": ActionType.Replace,
    "Break in Series": ActionType.Replace,
}

#: Per-country lifecycle state used for the demo run (mix of a routine revision and a flagged break).
SOVEREIGN_SUBMISSION_TYPES: Dict[str, str] = {
    "ca": "Revision",
    "us": "Break in Series",
    "gb": "First Submission",
}

#: Approximate share of GB's synthetic components deliberately corrupted to exercise the quarantine path.
INVALID_RECORD_RATE: float = 0.15


def _build_time_series_code(dimensions: Dict[str, str]) -> str:
    """Joins the 11 BIS_LBS dimensions into a dot-separated TIME_SERIES_CODE.

    Args:
        dimensions: Mapping of every dimension name in `DSD_DIMENSIONS` to its code value.

    Returns:
        The dot-separated composite SDMx key, e.g. ``"Q.S.C.A.CAD.D.5J.A.CA.A.5J"``.
    """
    return ".".join(dimensions[dim] for dim in DSD_DIMENSIONS)


def _make_micro_rows(
    base_dimensions: Dict[str, str],
    components: List[tuple],
) -> List[Dict[str, object]]:
    """Expands (L_DENOM, L_CURR_TYPE, BANK_CODE, OBS_VALUE[, overrides]) tuples into micro rows.

    Args:
        base_dimensions: The 9 fixed dimensions shared by all rows in a scenario
            (all `DSD_DIMENSIONS` except `L_DENOM` and `L_CURR_TYPE`).
        components: Tuples of `(l_denom, l_curr_type, bank_code, obs_value)`, optionally
            followed by a dimension-override dict (e.g. `{"L_CP_SECTOR": "H"}`) used to
            inject deliberately invalid combinations for quarantine-path testing.

    Returns:
        A list of dicts, one per component, matching the strict `MICRO_COLUMNS` schema.
    """
    rows: List[Dict[str, object]] = []
    for l_denom, l_curr_type, bank_code, obs_value, *overrides in components:
        dims = {**base_dimensions, "L_DENOM": l_denom, "L_CURR_TYPE": l_curr_type, **(overrides[0] if overrides else {})}
        rows.append(
            {
                "TIME_SERIES_CODE": _build_time_series_code(dims),
                "BANK_CODE": bank_code,
                "DATE": REPORTING_DATE,
                "IBS_AGG": IBS_AGG_CODE,
                "OBS_VALUE": float(obs_value),
            }
        )
    return rows


def generate_micro_transactions() -> Dict[str, pd.DataFrame]:
    """Generates synthetic, sovereign-isolated bank-level LBS micro-data per country.

    Models three separate national micro-data tables:
    ``dbw_sovereignshield.sovereign_shield.lbs_micro_transactions_ca``, ``_us``, and ``_gb``.

    Scenario A (Canada, `L_REP_CTY = 'CA'`): components (Domestic + Foreign +
    Unallocated) sum to exactly the `TO1.A` aggregate, satisfying the
    `LBS_CC01` consistency check, and no single bank holds >= 60% of any
    `TIME_SERIES_CODE`.

    Scenario B (United States, `L_REP_CTY = 'US'`): components sum to 1000
    while the `TO1.A` aggregate sums to 1500, deliberately failing
    `LBS_CC01`, and `BANK_US_1` holds 70% of the `TO1.A` aggregate, triggering
    the dominance rule.

    Scenario C (United Kingdom, `L_REP_CTY = 'GB'`): a mostly clean, reconciling
    submission (same `LBS_CC01` pattern as Canada) with `INVALID_RECORD_RATE`
    (~15%) of its components deliberately corrupted to exercise the quarantine
    path: a negative `OBS_VALUE` (breaks `LBS_CC01` reconciliation), a
    Household (`H`) sector holding Debt securities (`D`) instruments (a
    non-permitted sector-instrument pairing for LBS reporting), and a
    'domestic bank' (`L_REP_BANK_TYPE = 'D'`) declared with a foreign parent
    country (a logically inconsistent bank-type/parent-country combination).

    Returns:
        A dict keyed by lower-case country code (`'ca'`, `'us'`, `'gb'`), each
        value a pandas DataFrame with exactly the 5 columns in `MICRO_COLUMNS`.
    """
    # ------------------------------------------------------------------
    # Scenario A: Canada (CA) — clean submission, publicly publishable.
    # LBS_CC01: TO1:A (total) = ISO:D (domestic) + TO1:F (foreign) + UN9:U (unallocated)
    # ------------------------------------------------------------------
    ca_base = {
        "FREQ": "Q",
        "L_MEASURE": "S",
        "L_POSITION": "C",
        "L_INSTR": "A",
        "L_PARENT_CTY": "5J",
        "L_REP_BANK_TYPE": "A",
        "L_REP_CTY": "CA",
        "L_CP_SECTOR": "A",
        "L_CP_COUNTRY": "5J",
    }
    ca_components = [
        # Domestic currency (CAD:D) -> total 400
        ("CAD", "D", "BANK_CA_1", 200.0),
        ("CAD", "D", "BANK_CA_2", 200.0),
        # Foreign currencies (TO1:F) -> total 500
        ("TO1", "F", "BANK_CA_1", 250.0),
        ("TO1", "F", "BANK_CA_2", 250.0),
        # Unallocated currency type (UN9:U) -> total 100
        ("UN9", "U", "BANK_CA_3", 100.0),
        # All-currencies aggregate (TO1:A) -> total 1000 = 400 + 500 + 100 (LBS_CC01 passes)
        # Spread so no bank reaches the 60% dominance threshold.
        ("TO1", "A", "BANK_CA_1", 400.0),
        ("TO1", "A", "BANK_CA_2", 400.0),
        ("TO1", "A", "BANK_CA_3", 200.0),
    ]
    df_ca = pd.DataFrame(_make_micro_rows(ca_base, ca_components), columns=MICRO_COLUMNS)

    # ------------------------------------------------------------------
    # Scenario B: United States (US) — dirty submission, market dominant.
    # LBS_CC01 intentionally fails: components sum to 1000, aggregate sums to 1500.
    # ------------------------------------------------------------------
    us_base = {**ca_base, "L_REP_CTY": "US"}
    us_components = [
        # Domestic currency (USD:D) -> total 400
        ("USD", "D", "BANK_US_1", 400.0),
        # Foreign currencies (TO1:F) -> total 500
        ("TO1", "F", "BANK_US_2", 500.0),
        # Unallocated currency type (UN9:U) -> total 100
        ("UN9", "U", "BANK_US_2", 100.0),
        # All-currencies aggregate (TO1:A) -> total 1500 != 1000 (LBS_CC01 fails)
        # BANK_US_1 holds 1050 / 1500 = 70% of the aggregate (dominance triggered).
        ("TO1", "A", "BANK_US_1", 1050.0),
        ("TO1", "A", "BANK_US_2", 450.0),
    ]
    df_us = pd.DataFrame(_make_micro_rows(us_base, us_components), columns=MICRO_COLUMNS)

    # ------------------------------------------------------------------
    # Scenario C: United Kingdom (GB) — mostly clean, with ~INVALID_RECORD_RATE
    # of components deliberately corrupted to exercise the quarantine path.
    # ------------------------------------------------------------------
    gb_base = {**ca_base, "L_REP_CTY": "GB"}
    gb_components = [
        # Domestic currency (GBP:D) -> total 600
        ("GBP", "D", "BANK_GB_1", 300.0),
        ("GBP", "D", "BANK_GB_2", 300.0),
        # Foreign currencies (TO1:F) -> total 500
        ("TO1", "F", "BANK_GB_1", 250.0),
        ("TO1", "F", "BANK_GB_2", 250.0),
        # Unallocated currency type (UN9:U) -> total 100
        ("UN9", "U", "BANK_GB_3", 100.0),
        # All-currencies aggregate (TO1:A) -> total 1200 = 600 + 500 + 100 (LBS_CC01 passes)
        ("TO1", "A", "BANK_GB_1", 480.0),
        ("TO1", "A", "BANK_GB_2", 480.0),
        ("TO1", "A", "BANK_GB_3", 240.0),

        # --- ~INVALID_RECORD_RATE (~15%) deliberately invalid records for quarantine testing ---
        # 1) Negative transaction amount -> breaks LBS_CC01 reconciliation math.
        ("GBP", "D", "BANK_GB_1", -150.0),
        # 2) Invalid sector-currency pairing: Household ('H') sector holding Debt securities ('D').
        ("EUR", "F", "BANK_GB_2", 50.0, {"L_CP_SECTOR": "H", "L_INSTR": "D"}),
        # 3) Mismatched bank_type/parent_country: a 'domestic bank' (D) cannot have a foreign parent.
        ("CHF", "F", "BANK_GB_3", 75.0, {"L_REP_BANK_TYPE": "D", "L_PARENT_CTY": "US"}),
    ]
    df_gb = pd.DataFrame(_make_micro_rows(gb_base, gb_components), columns=MICRO_COLUMNS)

    return {"ca": df_ca, "us": df_us, "gb": df_gb}


def aggregate_micro_to_macro(df_micro: pd.DataFrame, threshold: float = 0.60) -> pd.DataFrame:
    """Aggregates a single sovereign's bank-level micro-data into SDMx 3.0 macro time series.

    Groups by `['TIME_SERIES_CODE', 'DATE', 'IBS_AGG']`, sums `OBS_VALUE`, and
    applies the Configurable Dominance Rule: if any single bank's contribution
    to a `TIME_SERIES_CODE` total is >= `threshold`, the observation is marked
    restricted (`OBS_CONF = 'N'`); otherwise it is free for publication
    (`OBS_CONF = 'F'`). All observations are tagged `OBS_STATUS = 'A'` (Normal).

    Args:
        df_micro: Bank-level micro-data matching the `MICRO_COLUMNS` schema,
            for a single reporting country.
        threshold: Minimum single-bank contribution share (0.0-1.0) that
            triggers restricted confidentiality. Defaults to 0.60.

    Returns:
        A macro DataFrame with columns `TIME_SERIES_CODE`, `DATE`, `IBS_AGG`,
        `OBS_VALUE`, `MAX_BANK_SHARE`, `OBS_CONF`, and `OBS_STATUS`.
    """
    group_keys = ["TIME_SERIES_CODE", "DATE", "IBS_AGG"]

    # 1. Total macro OBS_VALUE per SDMx time series.
    df_macro = df_micro.groupby(group_keys, as_index=False)["OBS_VALUE"].sum()

    # 2. Per-bank contribution within each time series, then the max share.
    df_bank_totals = df_micro.groupby(group_keys + ["BANK_CODE"], as_index=False)["OBS_VALUE"].sum()
    df_bank_totals = df_bank_totals.rename(columns={"OBS_VALUE": "BANK_OBS_VALUE"})
    df_bank_totals = df_bank_totals.merge(df_macro, on=group_keys, how="left")
    df_bank_totals["BANK_SHARE"] = df_bank_totals["BANK_OBS_VALUE"] / df_bank_totals["OBS_VALUE"]

    df_max_share = df_bank_totals.groupby(group_keys, as_index=False)["BANK_SHARE"].max()
    df_max_share = df_max_share.rename(columns={"BANK_SHARE": "MAX_BANK_SHARE"})

    df_macro = df_macro.merge(df_max_share, on=group_keys, how="left")

    # 3. Configurable Dominance Rule.
    df_macro["OBS_CONF"] = np.where(df_macro["MAX_BANK_SHARE"] >= threshold, "N", "F")

    # 4. Standard observation status.
    df_macro["OBS_STATUS"] = "A"

    return df_macro[group_keys + ["OBS_VALUE", "MAX_BANK_SHARE", "OBS_CONF", "OBS_STATUS"]]


def fetch_bis_lbs_dsd(dsd_url: str = BIS_LBS_DSD_URL) -> DataStructureDefinition:
    """Fetches the live BIS_LBS Data Structure Definition from the BIS REST API.

    Args:
        dsd_url: The SDMx REST endpoint returning the BIS_LBS DSD (and its
            referenced artefacts, e.g. codelists and concepts).

    Returns:
        The `DataStructureDefinition` for BIS_LBS, as parsed by `pysdmx`.

    Raises:
        ValueError: If the fetched message contains no DSD.
    """
    message = sdmx_io.read_sdmx(dsd_url, validate=False)
    dsds = message.get_data_structure_definitions()
    if not dsds:
        raise ValueError(f"No DataStructureDefinition found at '{dsd_url}'.")
    return dsds[0]


def generate_sdmx_ml(
    df_macro: pd.DataFrame,
    country_code: str,
    submission_type: str = "First Submission",
    dsd: Optional[DataStructureDefinition] = None,
) -> str:
    """Serializes an aggregated macro DataFrame into a sovereign SDMx 3.0 XML (ML) payload.

    Unpacks the dot-separated `TIME_SERIES_CODE` into its 11 primary BIS_LBS
    dimensions, builds a sovereign sender `Header` (Bank of Canada / Federal
    Reserve System, keyed by `country_code`), configures the dataset lifecycle
    action (`Information`, `Append`, or `Replace`) and `OBS_STATUS` according to
    `submission_type`, and writes the resulting structure-specific SDMx-ML 3.0
    data message to `data/{country_code}_submission_2026_Q1.xml`.

    Args:
        df_macro: Aggregated macro DataFrame, as returned by `aggregate_micro_to_macro`.
        country_code: Lower-case ISO country code (e.g. `'ca'`) used to name the
            output file, select the sovereign sender, and identify the submission.
        submission_type: One of `'First Submission'`, `'Revision'`, or
            `'Break in Series'`. Controls the SDMx dataset action and whether
            `OBS_STATUS` is forced to `'B'` (Break in series). Defaults to
            `'First Submission'`.
        dsd: The live BIS_LBS `DataStructureDefinition` used to build the SDMx
            schema. Fetched via `fetch_bis_lbs_dsd()` if not supplied.

    Returns:
        The serialized SDMx 3.0 XML (ML) string that was written to disk.

    Raises:
        ValueError: If `submission_type` is not a recognized lifecycle state.
    """
    if submission_type not in SUBMISSION_ACTIONS:
        raise ValueError(
            f"Unknown submission_type '{submission_type}'. Expected one of: "
            f"{', '.join(SUBMISSION_ACTIONS)}."
        )
    if dsd is None:
        dsd = fetch_bis_lbs_dsd()

    df_obs = df_macro["TIME_SERIES_CODE"].str.split(".", expand=True)
    df_obs.columns = DSD_DIMENSIONS
    df_obs["TIME_PERIOD"] = df_macro["DATE"].to_numpy()
    df_obs["OBS_VALUE"] = df_macro["OBS_VALUE"].to_numpy()
    # A Break in Series overrides every observation's status to flag the structural change.
    df_obs["OBS_STATUS"] = "B" if submission_type == "Break in Series" else df_macro["OBS_STATUS"].to_numpy()
    df_obs["OBS_CONF"] = df_macro["OBS_CONF"].to_numpy()

    schema = Schema(
        context="datastructure",
        agency=dsd.agency,
        id=dsd.id,
        components=dsd.components,
        version=dsd.version,
    )
    dataset_action = SUBMISSION_ACTIONS[submission_type]
    dataset = PandasDataset(structure=schema, data=df_obs, action=dataset_action)

    sender = SOVEREIGN_SENDERS.get(country_code, Organisation(id="ZZZ"))
    dataset_id = f"{country_code.upper()}_{IBS_AGG_CODE}_{REPORTING_DATE.replace('-', '')}"
    header = Header(
        id=str(uuid.uuid4()),
        test=False,
        prepared=datetime.now(timezone.utc),
        sender=sender,
        dataset_action=dataset_action,
        dataset_id=dataset_id,
    )

    xml_payload = sdmx_io.write_sdmx(dataset, Format.DATA_SDMX_ML_3_0, header=header)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{country_code}_submission_2026_Q1.xml")
    with open(output_path, "w", encoding="utf-8") as xml_file:
        xml_file.write(xml_payload)

    return xml_payload


if __name__ == "__main__":
    print("Fetching live BIS_LBS Data Structure Definition from the BIS REST API...")
    bis_lbs_dsd = fetch_bis_lbs_dsd()
    print(f"Fetched DSD '{bis_lbs_dsd.agency}:{bis_lbs_dsd.id}({bis_lbs_dsd.version})'.")

    print("\nGenerating sovereign-isolated synthetic LBS micro-data (CA clean / US dirty & dominant)...")
    micro_by_country = generate_micro_transactions()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for country_code, df_micro in micro_by_country.items():
        micro_csv_path = os.path.join(OUTPUT_DIR, f"micro_transactions_{country_code}.csv")
        df_micro.to_csv(micro_csv_path, index=False)
        print(f"Saved raw micro-data for {country_code.upper()} -> {micro_csv_path}")

    submission_summary: List[Dict[str, object]] = []
    for country_code, df_micro in micro_by_country.items():
        submission_type = SOVEREIGN_SUBMISSION_TYPES.get(country_code, "First Submission")
        sender = SOVEREIGN_SENDERS.get(country_code, Organisation(id="ZZZ"))

        print(f"\n=== Sovereign submission: {country_code.upper()} ({submission_type}) ===")
        print(f"--- Micro-Data: dbw_sovereignshield.sovereign_shield.lbs_micro_transactions_{country_code} ---")
        print(df_micro.to_string(index=False))

        df_macro = aggregate_micro_to_macro(df_micro, threshold=DOMINANCE_THRESHOLD)
        print(f"\n--- Macro-Data: SDMx 3.0 Aggregated Time Series ({country_code.upper()}) ---")
        print(df_macro.to_string(index=False))

        generate_sdmx_ml(df_macro, country_code, submission_type=submission_type, dsd=bis_lbs_dsd)
        output_path = os.path.join(OUTPUT_DIR, f"{country_code}_submission_2026_Q1.xml")
        submission_summary.append(
            {
                "country": country_code.upper(),
                "sender": f"{sender.id} ({sender.name})",
                "submission_type": submission_type,
                "dataset_action": SUBMISSION_ACTIONS[submission_type].value,
                "series_count": len(df_macro),
                "restricted_series": int((df_macro["OBS_CONF"] == "N").sum()),
                "output_path": output_path,
            }
        )

    print("\n--- Execution Summary ---")
    for entry in submission_summary:
        print(
            f"[{entry['country']}] sender={entry['sender']} | "
            f"lifecycle={entry['submission_type']} (action={entry['dataset_action']}) | "
            f"{entry['series_count']} series aggregated, "
            f"{entry['restricted_series']} restricted (OBS_CONF='N') -> {entry['output_path']}"
        )
