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
* United Kingdom (``GB``): three isolated, deliberately corrupted reconciliation
  groups to exercise the quarantine path end-to-end, each using only real,
  permitted BIS codes (no fabricated placeholders) and genuinely detected by
  ``SDMxRuleValidator``:

  1. Cross-check aggregation mismatch (``LBS_CC01``): Domestic + Foreign +
     Unallocated currency components deliberately do not sum to the ``TO1.A``
     aggregate.
  2. Currency breakdown mismatch (``LBS_CC02``): a net negative ``EUR:F`` leg
     among the 5 mandatory currencies breaks the ``TO1.F`` reconciliation.
     Negative observations are valid SDMx data; the failure is the broken
     cross-check, not the sign.
  3. Sector cross-check violation (``LBS_CC:04``): Banks (``B``) + Non-bank
     (``N``) deliberately do not sum to the ``All sectors (A)`` aggregate.
"""

from __future__ import annotations

import inspect
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

#: Aggregation framework code. 'LBSR' is the BIS Locational Banking Statistics
#: restated basis, the concrete example this reference architecture validates against.
AGG_CODE_DEFAULT: str = "LBSR"

#: Default share of a single bank's contribution that triggers OBS_CONF = 'N'.
DOMINANCE_THRESHOLD: float = 0.60

#: Strict, required schema for each sovereign micro-data table.
MICRO_COLUMNS: List[str] = ["TIME_SERIES_CODE", "BANK_CODE", "DATE", "AGG_CODE", "OBS_VALUE"]

#: Live BIS REST endpoint exposing the BIS_LBS Data Structure Definition (DSD).
BIS_LBS_DSD_URL: str = "https://stats.bis.org/api/v1/datastructure/BIS/BIS_LBS/latest?references=all"


def _resolve_repo_root() -> str:
    """Repo root, independent of the process's working directory.

    Databricks runs a spark_python_task via ``exec(compile(source, filename, 'exec'))``,
    so ``__file__`` is undefined for an entry point. The compiled code object still
    carries the real path, which the current frame exposes.
    """
    module_file = globals().get("__file__")

    if not module_file:
        frame = inspect.currentframe()
        if frame is not None and os.path.sep in frame.f_code.co_filename:
            module_file = frame.f_code.co_filename

    if not module_file:
        return os.getcwd()

    return os.path.dirname(os.path.dirname(os.path.abspath(module_file)))


_REPO_ROOT: str = _resolve_repo_root()

#: Directory where sovereign SDMx-ML submission files are written. The receiving
#: side reads the same location, so it is the contract between the two pipeline
#: tasks and has to be set explicitly wherever the repo tree is not writable.
OUTPUT_DIR: str = os.environ.get(
    "SOVEREIGNSHIELD_SUBMISSION_DIR", os.path.join(_REPO_ROOT, "data")
)

#: Submission cycles, in the order a reporting body would file them. Each writes a
#: complete set of national submissions into its own subdirectory, so the receiving
#: organisation processes one arrival at a time rather than a merged pile of files.
SUBMISSION_CYCLES: tuple = ("baseline", "revision")

#: Collection hierarchy under the volume. BIS publishes several banking datasets
#: under International Banking Statistics; naming the family and the dataset keeps
#: a second collection from landing on top of this one.
STATISTICAL_FAMILY: str = "IBS"
DATASET_CODE: str = "LBS"

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

#: Per-country lifecycle state used for the demo run. The baseline is each body's
#: first filing for the quarter; the revision re-reports the same series keys, which
#: is a Replace in SDMx terms regardless of whether the hub ends up accepting it.
SOVEREIGN_SUBMISSION_TYPES: Dict[str, str] = {
    "ca": "First Submission",
    "us": "First Submission",
    "gb": "First Submission",
}

#: Lifecycle state for a re-filing of a quarter already submitted.
REVISION_SUBMISSION_TYPES: Dict[str, str] = {
    "ca": "Revision",
    "us": "Break in Series",
    "gb": "Revision",
}


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
            followed by a dimension-override dict (e.g. `{"L_CP_COUNTRY": "FR"}`) used to
            isolate a deliberately-corrupted reconciliation group from the rest of a
            scenario's components for quarantine-path testing.

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
                "AGG_CODE": AGG_CODE_DEFAULT,
                "OBS_VALUE": float(obs_value),
            }
        )
    return rows


def generate_micro_transactions(cycle: str = "baseline") -> Dict[str, pd.DataFrame]:
    """Generates synthetic, sovereign-isolated bank-level LBS micro-data per country.

    Models three separate national micro-data tables:
    ``dbw_sovereignshield.sovereign_shield.lbs_micro_transactions_ca``, ``_us``, and ``_gb``.

    Confidentiality and quality are orthogonal, and the two cycles keep them
    visibly separate. Confidentiality is the *reporting* country's decision, taken
    here from the dominance threshold and travelling in the submission as
    ``OBS_CONF``. Quality is the *receiving* organisation's decision, taken by
    re-running ``checks_lbs.xls`` over the submitted file. A dominant bank makes
    an observation confidential; it does not make the submission wrong.

    ``baseline`` — every country reconciles against every BIS cross-check, so all
    three publish. They differ only in confidentiality: Canada spreads its
    positions across three banks and publishes freely, while ``BANK_US_1`` holds
    70% of the US ``TO1:A`` aggregate, so those observations are restricted
    (``OBS_CONF = 'N'``) despite being arithmetically clean.

    ``revision`` — each country re-reports the same series keys with a genuine
    arithmetic break, using only real BIS codes (no fabricated codelist values),
    each detected by `SDMxRuleValidator` against the published workbook:

    * Canada breaks the currency-type cross-check: the domestic leg is revised
      down while the ``TO1:A`` aggregate is not, so ``D + F + U`` no longer
      reconciles.
    * The United States breaks the same cross-check from the other side: the
      aggregate is revised up while its components are unchanged.
    * The United Kingdom breaks the currency breakdown and the sector
      cross-check, in two groups isolated from each other by ``L_CURR_TYPE``.

    Because quarantine is atomic per country-quarter, the revision is rejected
    whole and the published baseline stays ``IS_CURRENT``.

    Args:
        cycle: ``"baseline"`` or ``"revision"``.

    Returns:
        A dict keyed by lower-case country code (`'ca'`, `'us'`, `'gb'`), each
        value a pandas DataFrame with exactly the 5 columns in `MICRO_COLUMNS`.
    """
    if cycle not in SUBMISSION_CYCLES:
        raise ValueError(f"cycle must be one of {SUBMISSION_CYCLES}, got {cycle!r}")
    revision = cycle == "revision"

    # ------------------------------------------------------------------
    # Canada (CA). Baseline: TO1:A (1000) = CAD:D (400) + TO1:F (500) + UN9:U (100),
    # spread across three banks so nothing reaches the dominance threshold.
    # Revision: the domestic leg drops to 300 while the aggregate is re-reported
    # unchanged, so the components no longer sum to it.
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
    ca_domestic_leg = 150.0 if revision else 200.0
    ca_components = [
        # Domestic currency (CAD:D) -> 400 at baseline, 300 on revision.
        ("CAD", "D", "BANK_CA_1", ca_domestic_leg),
        ("CAD", "D", "BANK_CA_2", ca_domestic_leg),
        # Foreign currencies (TO1:F) -> 500.
        ("TO1", "F", "BANK_CA_1", 250.0),
        ("TO1", "F", "BANK_CA_2", 250.0),
        # Unallocated currency type (UN9:U) -> 100.
        ("UN9", "U", "BANK_CA_3", 100.0),
        # All-currencies aggregate (TO1:A) -> 1000, unchanged by the revision.
        ("TO1", "A", "BANK_CA_1", 400.0),
        ("TO1", "A", "BANK_CA_2", 400.0),
        ("TO1", "A", "BANK_CA_3", 200.0),
    ]
    df_ca = pd.DataFrame(_make_micro_rows(ca_base, ca_components), columns=MICRO_COLUMNS)

    # ------------------------------------------------------------------
    # United States (US). Market-dominant in both cycles: BANK_US_1 holds 70% of
    # TO1:A, so those observations are confidential either way. Baseline still
    # reconciles (1000 = 400 + 500 + 100); the revision inflates the aggregate to
    # 1500 while leaving the components alone.
    # ------------------------------------------------------------------
    us_base = {**ca_base, "L_REP_CTY": "US"}
    us_aggregate_scale = 1.5 if revision else 1.0
    us_components = [
        # Domestic currency (USD:D) -> 400.
        ("USD", "D", "BANK_US_1", 400.0),
        # Foreign currencies (TO1:F) -> 500.
        ("TO1", "F", "BANK_US_2", 500.0),
        # Unallocated currency type (UN9:U) -> 100.
        ("UN9", "U", "BANK_US_2", 100.0),
        # All-currencies aggregate (TO1:A). BANK_US_1 holds 70% at either scale.
        ("TO1", "A", "BANK_US_1", 700.0 * us_aggregate_scale),
        ("TO1", "A", "BANK_US_2", 300.0 * us_aggregate_scale),
    ]
    df_us = pd.DataFrame(_make_micro_rows(us_base, us_components), columns=MICRO_COLUMNS)

    # ------------------------------------------------------------------
    # United Kingdom (GB). Three reconciliation groups held apart by L_POSITION
    # and L_CURR_TYPE so a break in one cannot contaminate the others. Group 1
    # reconciles in both cycles; groups 2 and 3 break only on revision.
    # ------------------------------------------------------------------
    gb_base = {**ca_base, "L_REP_CTY": "GB"}
    # TO1:F is re-reported as 500 against unchanged legs summing to 400.
    gb_foreign_aggregate = 500.0 if revision else 400.0
    # All sectors (A) is re-reported as 500 against banks (300) + non-bank (150).
    gb_all_sectors = 500.0 if revision else 450.0
    gb_components = [
        # --- Group 1: currency-type cross-check, reconciles in both cycles ---
        # 900 = 300 (GBP:D) + 500 (TO1:F) + 100 (UN9:U).
        ("GBP", "D", "BANK_GB_1", 150.0),
        ("GBP", "D", "BANK_GB_2", 150.0),
        ("TO1", "F", "BANK_GB_2", 250.0),
        ("TO1", "F", "BANK_GB_3", 250.0),
        # Left with a single reporter: 100% of this series is one bank's position, so
        # it stays restricted and gives the column mask something to actually withhold.
        ("UN9", "U", "BANK_GB_3", 100.0),
        ("TO1", "A", "BANK_GB_1", 400.0),
        ("TO1", "A", "BANK_GB_2", 300.0),
        ("TO1", "A", "BANK_GB_3", 200.0),

        # --- Group 2: currency breakdown, breaks on revision ---
        # TO1:F must equal the 5 mandatory currencies plus TO3:F. The EUR:F leg is a
        # net negative position, which is valid SDMx data: 100-50+100+100+100+50 = 400.
        # L_POSITION='L' isolates this group from Group 1, and L_POSITION is never
        # itself a reconciliation target, so it cannot trigger spurious failures.
        ("USD", "F", "BANK_GB_1", 50.0, {"L_POSITION": "L"}),
        ("USD", "F", "BANK_GB_2", 50.0, {"L_POSITION": "L"}),
        # Single reporter and signed: dominance is measured on absolute contribution,
        # so a lone negative leg is restricted for concentration, not for its sign.
        ("EUR", "F", "BANK_GB_2", -50.0, {"L_POSITION": "L"}),
        ("JPY", "F", "BANK_GB_1", 55.0, {"L_POSITION": "L"}),
        ("JPY", "F", "BANK_GB_3", 45.0, {"L_POSITION": "L"}),
        ("CHF", "F", "BANK_GB_2", 50.0, {"L_POSITION": "L"}),
        ("CHF", "F", "BANK_GB_3", 50.0, {"L_POSITION": "L"}),
        ("GBP", "F", "BANK_GB_1", 50.0, {"L_POSITION": "L"}),
        ("GBP", "F", "BANK_GB_2", 50.0, {"L_POSITION": "L"}),
        ("TO3", "F", "BANK_GB_2", 50.0, {"L_POSITION": "L"}),
        ("TO1", "F", "BANK_GB_1", gb_foreign_aggregate / 2, {"L_POSITION": "L"}),
        ("TO1", "F", "BANK_GB_2", gb_foreign_aggregate / 2, {"L_POSITION": "L"}),

        # --- Group 3: sector cross-check, breaks on revision ---
        # All sectors (A) = Banks (B) + Non-bank (N). Shares Group 2's L_POSITION='L'
        # plane but is isolated from it by L_CURR_TYPE='D'.
        ("GBP", "D", "BANK_GB_1", gb_all_sectors / 2, {"L_POSITION": "L", "L_CP_SECTOR": "A"}),
        ("GBP", "D", "BANK_GB_2", gb_all_sectors / 2, {"L_POSITION": "L", "L_CP_SECTOR": "A"}),
        ("GBP", "D", "BANK_GB_1", 150.0, {"L_POSITION": "L", "L_CP_SECTOR": "B"}),
        ("GBP", "D", "BANK_GB_2", 150.0, {"L_POSITION": "L", "L_CP_SECTOR": "B"}),
        ("GBP", "D", "BANK_GB_3", 150.0, {"L_POSITION": "L", "L_CP_SECTOR": "N"}),
    ]
    df_gb = pd.DataFrame(_make_micro_rows(gb_base, gb_components), columns=MICRO_COLUMNS)

    return {"ca": df_ca, "us": df_us, "gb": df_gb}


def aggregate_micro_to_macro(df_micro: pd.DataFrame, threshold: float = 0.60) -> pd.DataFrame:
    """Aggregates a single sovereign's bank-level micro-data into SDMx 3.0 macro time series.

    Groups by `['TIME_SERIES_CODE', 'DATE', 'AGG_CODE']`, sums `OBS_VALUE`, and
    applies the Configurable Dominance Rule: if any single bank's contribution
    to a `TIME_SERIES_CODE` total is >= `threshold`, the observation is marked
    restricted (`OBS_CONF = 'N'`); otherwise it is free for publication
    (`OBS_CONF = 'F'`). All observations are tagged `OBS_STATUS = 'A'` (Normal).

    Dominance is measured on absolute contributions. LBS observations are signed,
    so a signed share is not a meaningful disclosure measure: offsetting positions
    can drive the denominator to zero or make a single bank's share exceed 1.

    Observations whose total nets to exactly zero are dropped, since SDMx does not
    report zero-valued positions.

    Args:
        df_micro: Bank-level micro-data matching the `MICRO_COLUMNS` schema,
            for a single reporting country.
        threshold: Minimum single-bank contribution share (0.0-1.0) that
            triggers restricted confidentiality. Defaults to 0.60.

    Returns:
        A macro DataFrame with columns `TIME_SERIES_CODE`, `DATE`, `AGG_CODE`,
        `OBS_VALUE`, `MAX_BANK_SHARE`, `OBS_CONF`, and `OBS_STATUS`.
    """
    group_keys = ["TIME_SERIES_CODE", "DATE", "AGG_CODE"]

    # 1. Total macro OBS_VALUE per SDMx time series.
    df_macro = df_micro.groupby(group_keys, as_index=False)["OBS_VALUE"].sum()

    # 2. Per-bank contribution within each time series, then the max absolute share.
    df_bank_totals = df_micro.groupby(group_keys + ["BANK_CODE"], as_index=False)["OBS_VALUE"].sum()
    df_bank_totals = df_bank_totals.rename(columns={"OBS_VALUE": "BANK_OBS_VALUE"})
    df_bank_totals["ABS_BANK_OBS_VALUE"] = df_bank_totals["BANK_OBS_VALUE"].abs()

    df_abs_totals = df_bank_totals.groupby(group_keys, as_index=False)["ABS_BANK_OBS_VALUE"].sum()
    df_abs_totals = df_abs_totals.rename(columns={"ABS_BANK_OBS_VALUE": "ABS_TOTAL"})
    df_bank_totals = df_bank_totals.merge(df_abs_totals, on=group_keys, how="left")

    # A series with no reported exposure at all has no dominant contributor to protect.
    df_bank_totals["BANK_SHARE"] = np.where(
        df_bank_totals["ABS_TOTAL"] > 0,
        df_bank_totals["ABS_BANK_OBS_VALUE"] / df_bank_totals["ABS_TOTAL"].replace(0, np.nan),
        0.0,
    )

    df_max_share = df_bank_totals.groupby(group_keys, as_index=False)["BANK_SHARE"].max()
    df_max_share = df_max_share.rename(columns={"BANK_SHARE": "MAX_BANK_SHARE"})

    df_macro = df_macro.merge(df_max_share, on=group_keys, how="left")

    # 3. Configurable Dominance Rule.
    df_macro["OBS_CONF"] = np.where(df_macro["MAX_BANK_SHARE"] >= threshold, "N", "F")

    # 4. Standard observation status.
    df_macro["OBS_STATUS"] = "A"

    # 5. SDMx convention: zero-valued positions are not reported at all.
    df_macro = df_macro[df_macro["OBS_VALUE"] != 0]

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
    output_dir: Optional[str] = None,
) -> str:
    """Serializes an aggregated macro DataFrame into a sovereign SDMx 3.0 XML (ML) payload.

    Unpacks the dot-separated `TIME_SERIES_CODE` into its 11 primary BIS_LBS
    dimensions, builds a sovereign sender `Header` (Bank of Canada / Federal
    Reserve System, keyed by `country_code`), configures the dataset lifecycle
    action (`Information`, `Append`, or `Replace`) and `OBS_STATUS` according to
    `submission_type`, and writes the resulting structure-specific SDMx-ML 3.0
    data message as `{country_code}_submission_{YYYY-MM-DD}_{HHMMSS}.xml`.

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
        output_dir: Directory to file into. Defaults to `OUTPUT_DIR`.

    Returns:
        The path written. The filename carries a timestamp resolved at call time,
        so a caller cannot reconstruct it and must use this value.

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
    dataset_id = f"{country_code.upper()}_{AGG_CODE_DEFAULT}_{REPORTING_DATE.replace('-', '')}"
    header = Header(
        id=str(uuid.uuid4()),
        test=False,
        prepared=datetime.now(timezone.utc),
        sender=sender,
        dataset_action=dataset_action,
        dataset_id=dataset_id,
    )

    xml_payload = sdmx_io.write_sdmx(dataset, Format.DATA_SDMX_ML_3_0, header=header)

    target_dir = output_dir or OUTPUT_DIR
    os.makedirs(target_dir, exist_ok=True)
    # Timestamped to the second: a country may re-file the same period on the same
    # day, and a filing is evidence of what was sent when, so nothing here overwrites.
    # The reporting period stays in the observations rather than the name.
    filed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    output_path = os.path.join(target_dir, f"{country_code}_submission_{filed_at}.xml")
    with open(output_path, "w", encoding="utf-8") as xml_file:
        xml_file.write(xml_payload)

    return output_path


if __name__ == "__main__":
    print("Fetching live BIS_LBS Data Structure Definition from the BIS REST API...")
    bis_lbs_dsd = fetch_bis_lbs_dsd()
    print(f"Fetched DSD '{bis_lbs_dsd.agency}:{bis_lbs_dsd.id}({bis_lbs_dsd.version})'.")

    # Partitioned by the date the filing arrived, not the period it reports. A revision
    # to 2026-Q1 filed in November is a November arrival, and an auditor asking what was
    # held on a given date needs the former.
    arrival = datetime.now(timezone.utc)
    arrival_root = os.path.join(
        OUTPUT_DIR,
        STATISTICAL_FAMILY,
        DATASET_CODE,
        arrival.strftime("%Y"),
        arrival.strftime("%m"),
        arrival.strftime("%d"),
    )
    print(f"Submissions will be filed under {arrival_root}")

    submission_summary: List[Dict[str, object]] = []

    for sequence, cycle in enumerate(SUBMISSION_CYCLES, start=1):
        # Sequence-prefixed so the receiving side can process arrivals in filing order by
        # sorting, rather than by knowing what the cycles are called. Zero-padded because
        # the whole path is sorted lexically and a tenth filing must not precede a second.
        cycle_dir = os.path.join(arrival_root, f"{sequence:02d}_{cycle}")
        os.makedirs(cycle_dir, exist_ok=True)

        print(f"\n{'#' * 70}\n# Reporting cycle: {cycle}\n{'#' * 70}")
        micro_by_country = generate_micro_transactions(cycle=cycle)

        for country_code, df_micro in micro_by_country.items():
            micro_csv_path = os.path.join(cycle_dir, f"micro_transactions_{country_code}.csv")
            df_micro.to_csv(micro_csv_path, index=False)
            print(f"Saved raw micro-data for {country_code.upper()} -> {micro_csv_path}")

        lifecycle = (
            SOVEREIGN_SUBMISSION_TYPES if cycle == "baseline" else REVISION_SUBMISSION_TYPES
        )

        for country_code, df_micro in micro_by_country.items():
            submission_type = lifecycle.get(country_code, "First Submission")
            sender = SOVEREIGN_SENDERS.get(country_code, Organisation(id="ZZZ"))

            print(f"\n=== Sovereign submission: {country_code.upper()} ({submission_type}) ===")
            print(f"--- Micro-Data: lbs_micro_transactions_{country_code} ({cycle}) ---")
            print(df_micro.to_string(index=False))

            # Confidentiality is decided here, by the reporting country, from the
            # dominance threshold. Whether the submission is accepted is not.
            df_macro = aggregate_micro_to_macro(df_micro, threshold=DOMINANCE_THRESHOLD)
            print(f"\n--- Macro-Data: SDMx 3.0 Aggregated Time Series ({country_code.upper()}) ---")
            print(df_macro.to_string(index=False))

            filed_path = generate_sdmx_ml(
                df_macro,
                country_code,
                submission_type=submission_type,
                dsd=bis_lbs_dsd,
                output_dir=cycle_dir,
            )
            submission_summary.append(
                {
                    "cycle": cycle,
                    "country": country_code.upper(),
                    "sender": f"{sender.id} ({sender.name})",
                    "submission_type": submission_type,
                    "dataset_action": SUBMISSION_ACTIONS[submission_type].value,
                    "series_count": len(df_macro),
                    "restricted_series": int((df_macro["OBS_CONF"] == "N").sum()),
                    "output_path": filed_path,
                }
            )

    print("\n--- Execution Summary ---")
    for entry in submission_summary:
        print(
            f"[{entry['cycle']}/{entry['country']}] sender={entry['sender']} | "
            f"lifecycle={entry['submission_type']} (action={entry['dataset_action']}) | "
            f"{entry['series_count']} series aggregated, "
            f"{entry['restricted_series']} restricted (OBS_CONF='N') -> {entry['output_path']}"
        )
    print(
        "\nQuality is not decided here. The receiving organisation re-runs "
        "checks_lbs.xls over these files and rules on them independently."
    )
