"""Native SDMX 3.0 serialization for SovereignShield query results.

Turns the tabular shape held in Unity Catalog - a dot-separated
``TIME_SERIES_CODE`` plus one observation per row - into the wire formats a
statistical data portal is expected to speak:

* **SDMX-ML 3.0** structure-specific data messages (the archival format)
* **SDMX-JSON 2.0.0** data messages (the format a browser wants)
* **SDMX-CSV 2.0.0** (the standardised tabular format), plus a plain "tidy"
  CSV for analysts who just want a spreadsheet

SDMX 3.0.0 removed the Generic Data format, so ``StructureSpecificData`` is the
only XML data message the standard still defines. The ``output_type`` argument
is kept for forward compatibility but rejects anything else rather than
silently emitting a 2.1-era payload.

Serialization is delegated to ``pysdmx`` whenever it is importable, because it
writes against the published schemas and is already the engine behind
``generate_sovereign_submissions.py``. A dependency-free ElementTree writer
stands behind it so an export request never fails merely because the live BIS
structure endpoint is unreachable.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structure identity
# ---------------------------------------------------------------------------

#: Dataflow published by the BIS Data Portal for Locational Banking Statistics.
DATAFLOW_AGENCY = "BIS"
DATAFLOW_ID = "WS_LBS_D_PUB"
DATAFLOW_VERSION = "1.0"

#: Data structure the dataflow is defined against.
DSD_AGENCY = "BIS"
DSD_ID = "BIS_LBS"
DSD_VERSION = "1.0"

BIS_LBS_DSD_URL = os.getenv(
    "SOVEREIGNSHIELD_DSD_URL",
    "https://stats.bis.org/api/v1/datastructure/BIS/BIS_LBS/latest?references=all",
)

#: The 11 BIS_LBS dimensions in the exact order encoded in TIME_SERIES_CODE.
#: Segment 9 (``L_REP_CTY``) is the anchor the Unity Catalog row filter reads.
SDMX_DIMENSIONS: List[str] = [
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

TIME_DIMENSION = "TIME_PERIOD"
MEASURE = "OBS_VALUE"
OBS_ATTRIBUTES: List[str] = ["OBS_STATUS", "OBS_CONF"]

#: Position of L_REP_CTY, used by callers that need the reporting sovereign.
REP_CTY_SEGMENT = SDMX_DIMENSIONS.index("L_REP_CTY") + 1

#: SDMX-CSV 2.0.0 / SDMX-ML 3.0 dataset action codes.
ACTION_CODES = {
    "Information": "I",
    "Append": "A",
    "Replace": "R",
    "Delete": "D",
}

_SDMX_ML_NS = {
    "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v3_0/message",
    "com": "http://www.sdmx.org/resources/sdmxml/schemas/v3_0/common",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

_SDMX_JSON_SCHEMA = (
    "https://raw.githubusercontent.com/sdmx-twg/sdmx-json/master/data-message/"
    "tools/schemas/2.0.0/sdmx-json-data-schema.json"
)


class SdmxSerializationError(RuntimeError):
    """Raised when a payload cannot be expressed as valid SDMX."""


# ---------------------------------------------------------------------------
# Key handling
# ---------------------------------------------------------------------------


def parse_series_key(time_series_code: str) -> Dict[str, str]:
    """Splits one composite SDMx key into its 11 named dimensions.

    Raises:
        SdmxSerializationError: If the key does not carry exactly 11 segments.
    """
    segments = str(time_series_code).split(".")
    if len(segments) != len(SDMX_DIMENSIONS):
        raise SdmxSerializationError(
            f"TIME_SERIES_CODE '{time_series_code}' has {len(segments)} segment(s); "
            f"the BIS_LBS key requires {len(SDMX_DIMENSIONS)}."
        )
    return dict(zip(SDMX_DIMENSIONS, segments))


def explode_series_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Projects a query result into the flat SDMx component layout.

    The returned frame carries the 11 dimensions, ``TIME_PERIOD``, ``OBS_VALUE``
    and the observation-level attributes - exactly the components the BIS_LBS
    structure declares, and nothing else.

    Validation is per row via a segment count rather than
    ``str.split(expand=True)``: the latter pads short keys with NaN and sizes
    itself by the longest key, so one malformed row would silently misalign
    every dimension instead of raising.
    """
    if df.empty:
        return pd.DataFrame(columns=SDMX_DIMENSIONS + [TIME_DIMENSION, MEASURE] + OBS_ATTRIBUTES)

    if "TIME_SERIES_CODE" not in df.columns:
        raise SdmxSerializationError("Input frame has no TIME_SERIES_CODE column.")

    keys = df["TIME_SERIES_CODE"].astype(str)
    segment_counts = keys.str.count(r"\.") + 1
    malformed = keys[segment_counts != len(SDMX_DIMENSIONS)]
    if not malformed.empty:
        raise SdmxSerializationError(
            f"{len(malformed)} row(s) carry a malformed SDMx key, first: '{malformed.iloc[0]}'."
        )

    exploded = keys.str.split(".", expand=True)
    exploded.columns = SDMX_DIMENSIONS

    period_column = TIME_DIMENSION if TIME_DIMENSION in df.columns else "DATE"
    if period_column not in df.columns:
        raise SdmxSerializationError("Input frame has neither TIME_PERIOD nor DATE.")
    exploded[TIME_DIMENSION] = df[period_column].astype(str).to_numpy()

    exploded[MEASURE] = pd.to_numeric(df[MEASURE], errors="coerce").to_numpy() if MEASURE in df.columns else pd.NA

    for attribute in OBS_ATTRIBUTES:
        exploded[attribute] = df[attribute].to_numpy() if attribute in df.columns else ""

    return exploded.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Structure resolution
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def fetch_lbs_components(dsd_url: str = BIS_LBS_DSD_URL):
    """Fetches and caches the live BIS_LBS component list.

    Cached for the lifetime of the process: the DSD changes on the BIS release
    calendar, not per request, and an uncached fetch would put a third-party
    HTTP call on the critical path of every export.

    Returns:
        The pysdmx component list, or ``None`` when the structure cannot be
        retrieved - in which case the caller falls back to the local writer.
    """
    try:
        from pysdmx.io import read_sdmx

        message = read_sdmx(dsd_url, validate=False)
        structures = message.get_data_structure_definitions()
        if not structures:
            raise ValueError("Structure message contained no DataStructureDefinition.")
        return structures[0].components
    except Exception as exc:  # noqa: BLE001 - degraded mode is deliberate
        LOGGER.warning("Falling back to the local SDMx writer: %s", exc)
        return None


def structure_urn() -> str:
    """URN of the dataflow every message produced here is reported against."""
    return (
        "urn:sdmx:org.sdmx.infomodel.datastructure.Dataflow="
        f"{DATAFLOW_AGENCY}:{DATAFLOW_ID}({DATAFLOW_VERSION})"
    )


def _structure_id() -> str:
    return f"{DATAFLOW_AGENCY}_{DATAFLOW_ID}_{DATAFLOW_VERSION.replace('.', '_')}"


# ---------------------------------------------------------------------------
# SDMX-ML 3.0
# ---------------------------------------------------------------------------


def to_sdmx_ml_3_0(
    df: pd.DataFrame,
    output_type: str = "StructureSpecificData",
    sender_id: str = "SOVEREIGNSHIELD",
    sender_name: str = "SovereignShield Data Portal",
    dataset_action: str = "Information",
    dataset_id: Optional[str] = None,
    validate: bool = False,
) -> str:
    """Serializes query results as an SDMX-ML 3.0 data message.

    Args:
        df: Tabular result carrying ``TIME_SERIES_CODE`` and one row per observation.
        output_type: Only ``"StructureSpecificData"`` is defined by SDMX 3.0.0;
            the Generic Data format was removed from the standard.
        sender_id: Organisation id written into the message header.
        sender_name: Human-readable sender name.
        dataset_action: One of ``Information``, ``Append``, ``Replace``, ``Delete``.
        dataset_id: Optional dataset identifier for the header.
        validate: Round-trip the payload through the SDMx reader before
            returning it, so a malformed message is caught here rather than by
            the receiving institution.

    Returns:
        The serialized XML document.
    """
    if output_type != "StructureSpecificData":
        raise SdmxSerializationError(
            f"'{output_type}' is not an SDMX 3.0 data message. SDMX 3.0.0 removed "
            "GenericData; StructureSpecificData is the only defined XML data format."
        )
    if dataset_action not in ACTION_CODES:
        raise SdmxSerializationError(
            f"Unknown dataset action '{dataset_action}'. Expected one of {sorted(ACTION_CODES)}."
        )

    observations = explode_series_keys(df)
    components = fetch_lbs_components()

    if components is not None:
        try:
            payload = _write_with_pysdmx(
                observations, components, sender_id, sender_name, dataset_action, dataset_id
            )
        except Exception as exc:  # noqa: BLE001 - fall through to the local writer
            LOGGER.warning("pysdmx serialization failed, using the local writer: %s", exc)
            payload = _write_with_elementtree(
                observations, sender_id, sender_name, dataset_action, dataset_id
            )
    else:
        payload = _write_with_elementtree(
            observations, sender_id, sender_name, dataset_action, dataset_id
        )

    if validate:
        _assert_readable(payload)
    return payload


def _write_with_pysdmx(
    observations: pd.DataFrame,
    components,
    sender_id: str,
    sender_name: str,
    dataset_action: str,
    dataset_id: Optional[str],
) -> str:
    """Serializes through pysdmx, which writes against the published schemas."""
    import pysdmx.io as sdmx_io
    from pysdmx.io.format import Format
    from pysdmx.io.pd import PandasDataset
    from pysdmx.model import Organisation
    from pysdmx.model.dataflow import Schema
    from pysdmx.model.dataset import ActionType
    from pysdmx.model.message import Header

    frame = observations.copy()
    # A masked observation is absent, not zero: DDM nulls confidential values
    # for personas that are not entitled to read them.
    frame[MEASURE] = frame[MEASURE].map(lambda v: "" if pd.isna(v) else f"{v:g}")

    schema = Schema(
        context="dataflow",
        agency=DATAFLOW_AGENCY,
        id=DATAFLOW_ID,
        components=components,
        version=DATAFLOW_VERSION,
    )
    action = ActionType[dataset_action]
    dataset = PandasDataset(structure=schema, data=frame, action=action)
    header = Header(
        id=str(uuid.uuid4()),
        test=False,
        prepared=datetime.now(timezone.utc),
        sender=Organisation(id=sender_id, name=sender_name),
        dataset_action=action,
        dataset_id=dataset_id or f"{DATAFLOW_ID}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
    )
    return sdmx_io.write_sdmx(dataset, Format.DATA_SDMX_ML_3_0, header=header)


def _write_with_elementtree(
    observations: pd.DataFrame,
    sender_id: str,
    sender_name: str,
    dataset_action: str,
    dataset_id: Optional[str],
) -> str:
    """Degraded-mode writer used when the live structure cannot be resolved.

    Emits the SDMX 3.0 structure-specific shape without consulting the schemas,
    so the portal keeps serving downloads during a BIS outage. Messages written
    here are marked ``Test`` so a consumer can tell they were produced without
    structure validation.
    """
    for prefix, uri in _SDMX_ML_NS.items():
        ET.register_namespace(prefix, uri)

    mes = _SDMX_ML_NS["mes"]
    com = _SDMX_ML_NS["com"]
    structure_id = _structure_id()

    root = ET.Element(f"{{{mes}}}StructureSpecificData")
    header = ET.SubElement(root, f"{{{mes}}}Header")
    ET.SubElement(header, f"{{{mes}}}ID").text = str(uuid.uuid4())
    ET.SubElement(header, f"{{{mes}}}Test").text = "true"
    ET.SubElement(header, f"{{{mes}}}Prepared").text = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    sender = ET.SubElement(header, f"{{{mes}}}Sender", {"id": sender_id})
    ET.SubElement(sender, f"{{{com}}}Name", {"xml:lang": "en"}).text = sender_name

    structure = ET.SubElement(
        header,
        f"{{{mes}}}Structure",
        {
            "structureID": structure_id,
            "namespace": structure_urn(),
            "dimensionAtObservation": TIME_DIMENSION,
        },
    )
    structure_ref = ET.SubElement(structure, f"{{{com}}}Structure")
    ET.SubElement(
        structure_ref,
        "Ref",
        {
            "agencyID": DATAFLOW_AGENCY,
            "id": DATAFLOW_ID,
            "version": DATAFLOW_VERSION,
            "class": "Dataflow",
        },
    )
    if dataset_id:
        ET.SubElement(header, f"{{{mes}}}DataSetID").text = dataset_id

    dataset = ET.SubElement(
        root,
        f"{{{mes}}}DataSet",
        {"structureRef": structure_id, "action": dataset_action},
    )

    for key, group in _group_series(observations):
        series = ET.SubElement(dataset, "Series", key)
        for observation in group:
            ET.SubElement(series, "Obs", observation)

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def _group_series(observations: pd.DataFrame):
    """Yields ``(series key attributes, [observation attributes])`` pairs.

    Grouping is insertion-ordered so a re-export of an unchanged result set is
    byte-identical, which makes the payload diffable in an audit trail.
    """
    grouped: Dict[tuple, List[Dict[str, str]]] = {}
    for record in observations.to_dict(orient="records"):
        key = tuple(str(record[dimension]) for dimension in SDMX_DIMENSIONS)
        attributes = {TIME_DIMENSION: str(record[TIME_DIMENSION])}
        value = record.get(MEASURE)
        if not pd.isna(value):
            attributes[MEASURE] = f"{value:g}"
        for attribute in OBS_ATTRIBUTES:
            text = record.get(attribute)
            if text not in (None, "") and not pd.isna(text):
                attributes[attribute] = str(text)
        grouped.setdefault(key, []).append(attributes)

    for key, group in grouped.items():
        yield dict(zip(SDMX_DIMENSIONS, key)), group


def _assert_readable(xml_payload: str) -> None:
    """Confirms the emitted document parses back as an SDMx message."""
    try:
        from pysdmx.io import read_sdmx

        read_sdmx(xml_payload, validate=False)
        return
    except ImportError:
        # pysdmx defers its XML-extra check to call time, so a missing extra
        # surfaces from inside read_sdmx as well as from the import. Without a
        # reader, a well-formedness check is the strongest guarantee available -
        # and refusing the export would be the wrong call, since the payload was
        # produced by the fallback writer precisely because pysdmx was unusable.
        pass
    except Exception as exc:  # noqa: BLE001
        raise SdmxSerializationError(f"Generated SDMX-ML did not round-trip: {exc}") from exc

    try:
        ET.fromstring(xml_payload)  # noqa: S314 - payload produced in-process
    except ET.ParseError as exc:
        raise SdmxSerializationError(f"Generated SDMX-ML is not well-formed: {exc}") from exc


# ---------------------------------------------------------------------------
# SDMX-JSON 2.0.0
# ---------------------------------------------------------------------------


def to_sdmx_json_2_0_0(
    df: pd.DataFrame,
    sender_id: str = "SOVEREIGNSHIELD",
    sender_name: str = "SovereignShield Data Portal",
    dataset_action: str = "Information",
) -> str:
    """Serializes query results as an SDMX-JSON 2.0.0 data message."""
    observations = explode_series_keys(df)

    dimension_values: Dict[str, List[str]] = {d: [] for d in SDMX_DIMENSIONS}
    dimension_index: Dict[str, Dict[str, int]] = {d: {} for d in SDMX_DIMENSIONS}
    period_values: List[str] = []
    period_index: Dict[str, int] = {}
    attribute_values: Dict[str, List[str]] = {a: [] for a in OBS_ATTRIBUTES}
    attribute_index: Dict[str, Dict[str, int]] = {a: {} for a in OBS_ATTRIBUTES}

    def _position(value: str, values: List[str], index: Dict[str, int]) -> int:
        if value not in index:
            index[value] = len(values)
            values.append(value)
        return index[value]

    series: Dict[str, Dict[str, Any]] = {}
    for record in observations.to_dict(orient="records"):
        series_key = ":".join(
            str(_position(str(record[d]), dimension_values[d], dimension_index[d]))
            for d in SDMX_DIMENSIONS
        )
        period_position = _position(str(record[TIME_DIMENSION]), period_values, period_index)

        value = record.get(MEASURE)
        cell: List[Any] = [None if pd.isna(value) else float(value)]
        for attribute in OBS_ATTRIBUTES:
            text = record.get(attribute)
            if text in (None, "") or pd.isna(text):
                cell.append(None)
            else:
                cell.append(
                    _position(str(text), attribute_values[attribute], attribute_index[attribute])
                )

        series.setdefault(series_key, {"attributes": [], "observations": {}})
        series[series_key]["observations"][str(period_position)] = cell

    message = {
        "meta": {
            "schema": _SDMX_JSON_SCHEMA,
            "id": str(uuid.uuid4()),
            "test": False,
            "prepared": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "contentLanguages": ["en"],
            "sender": {"id": sender_id, "name": sender_name},
        },
        "data": {
            "dataSets": [{"action": dataset_action, "series": series}],
            "structures": [
                {
                    "dataSets": [0],
                    "links": [{"urn": structure_urn(), "rel": "self"}],
                    "dimensions": {
                        "series": [
                            {
                                "id": dimension,
                                "name": dimension,
                                "keyPosition": position,
                                "values": [{"id": v, "name": v} for v in dimension_values[dimension]],
                            }
                            for position, dimension in enumerate(SDMX_DIMENSIONS)
                        ],
                        "observation": [
                            {
                                "id": TIME_DIMENSION,
                                "name": "Time period",
                                "values": [{"id": v, "name": v} for v in period_values],
                            }
                        ],
                    },
                    "attributes": {
                        "observation": [
                            {
                                "id": attribute,
                                "name": attribute,
                                "values": [{"id": v, "name": v} for v in attribute_values[attribute]],
                            }
                            for attribute in OBS_ATTRIBUTES
                        ]
                    },
                }
            ],
        },
    }
    return json.dumps(message, indent=2)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def to_sdmx_csv_2_0_0(df: pd.DataFrame, dataset_action: str = "Information") -> str:
    """Serializes query results as SDMX-CSV 2.0.0.

    The standardised tabular format: every row is self-describing, carrying the
    structure it belongs to and the action it asserts, so a file can be
    round-tripped without an out-of-band agreement on column order.
    """
    if dataset_action not in ACTION_CODES:
        raise SdmxSerializationError(f"Unknown dataset action '{dataset_action}'.")

    observations = explode_series_keys(df)
    structure_reference = f"{DATAFLOW_AGENCY}:{DATAFLOW_ID}({DATAFLOW_VERSION})"

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["STRUCTURE", "STRUCTURE_ID", "ACTION"]
        + SDMX_DIMENSIONS
        + [TIME_DIMENSION, MEASURE]
        + OBS_ATTRIBUTES
    )
    for record in observations.to_dict(orient="records"):
        value = record.get(MEASURE)
        writer.writerow(
            ["dataflow", structure_reference, ACTION_CODES[dataset_action]]
            + [record[d] for d in SDMX_DIMENSIONS]
            + [record[TIME_DIMENSION], "" if pd.isna(value) else f"{value:g}"]
            + [_blank_if_missing(record.get(a)) for a in OBS_ATTRIBUTES]
        )
    return buffer.getvalue()


def to_tidy_csv(df: pd.DataFrame, columns: Optional[Sequence[str]] = None) -> str:
    """Serializes query results as a plain analyst-facing CSV.

    Keeps the composite key alongside the exploded dimensions so the file can
    be joined straight back to the Delta history.
    """
    observations = explode_series_keys(df)
    observations.insert(0, "TIME_SERIES_CODE", df["TIME_SERIES_CODE"].astype(str).to_numpy())

    for passthrough in ("IBS_AGG", "BATCH_STATUS", "QUALITY_STATUS"):
        if passthrough in df.columns:
            observations[passthrough] = df[passthrough].to_numpy()

    if columns:
        missing = [c for c in columns if c not in observations.columns]
        if missing:
            raise SdmxSerializationError(f"Unknown export column(s): {missing}")
        observations = observations[list(columns)]

    return observations.to_csv(index=False, lineterminator="\n")


def _blank_if_missing(value: Any) -> str:
    if value is None or value == "" or pd.isna(value):
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

#: Wire format -> (serializer, media type, file extension).
SERIALIZERS = {
    "sdmx-ml": (to_sdmx_ml_3_0, "application/xml", "xml"),
    "sdmx-json": (to_sdmx_json_2_0_0, "application/vnd.sdmx.data+json;version=2.0.0", "json"),
    "sdmx-csv": (to_sdmx_csv_2_0_0, "application/vnd.sdmx.data+csv;version=2.0.0", "csv"),
    "tidy-csv": (to_tidy_csv, "text/csv", "csv"),
}


def serialize(df: pd.DataFrame, wire_format: str, **kwargs) -> tuple[str, str, str]:
    """Serializes to a named wire format.

    Returns:
        ``(payload, media_type, file_extension)``.
    """
    if wire_format not in SERIALIZERS:
        raise SdmxSerializationError(
            f"Unsupported format '{wire_format}'. Expected one of {sorted(SERIALIZERS)}."
        )
    serializer, media_type, extension = SERIALIZERS[wire_format]
    return serializer(df, **kwargs), media_type, extension
