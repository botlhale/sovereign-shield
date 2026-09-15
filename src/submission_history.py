"""Submission identity and single-transaction Delta history for local verification."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake
from filelock import FileLock

from decimal_measures import decimal_text, decimal_value

NATURAL_KEY = ["TIME_SERIES_CODE", "DATE", "AGG_CODE"]
PAYLOAD_COLUMNS = ["OBS_VALUE", "OBS_STATUS", "OBS_CONF", "QUALITY_STATUS", "FAILED_RULE_ID", "BATCH_STATUS", "BATCH_FAILED_RULE_ID", "VALIDATION_NOTES"]
STRING_COLUMNS = NATURAL_KEY + [name for name in PAYLOAD_COLUMNS if name != "OBS_VALUE"] + ["SUBMISSION_ID", "SOURCE_SHA256", "RECORD_ID", "version_hash"]
TIME_COLUMNS = ["SUBMITTED_AT", "RECEIVED_AT", "VALID_FROM", "VALID_TO"]
HISTORY_COLUMNS = STRING_COLUMNS + ["OBS_VALUE"] + TIME_COLUMNS + ["IS_CURRENT"]


@dataclass(frozen=True)
class SubmissionContext:
    submission_id: str
    source_sha256: str
    submitted_at: datetime
    received_at: datetime

    def __post_init__(self):
        if not self.submission_id or len(self.submission_id) > 512:
            raise ValueError("A bounded, immutable submission ID is required.")
        if len(self.source_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.source_sha256):
            raise ValueError("SOURCE_SHA256 must be a SHA256 digest.")
        for value in (self.submitted_at, self.received_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Submission timestamps must be timezone-aware.")


def stable_hash(values):
    normalized = [None if value is None or pd.isna(value) else str(value) for value in values]
    return hashlib.sha256(json.dumps(normalized, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def prepare_submission(frame, context):
    if frame.empty:
        raise ValueError("Empty replacements require an explicit scope manifest.")
    required = set(NATURAL_KEY + ["OBS_VALUE", "OBS_STATUS", "OBS_CONF", "BATCH_STATUS", "QUALITY_STATUS"])
    if required - set(frame):
        raise ValueError(f"Missing validated submission columns: {sorted(required - set(frame))}.")
    source = frame.copy()
    key = NATURAL_KEY + (["BANK_CODE"] if "BANK_CODE" in source else [])
    if source.duplicated(key).any():
        raise ValueError("Duplicate observation in one submission.")
    scopes = source.assign(REPORTING_COUNTRY=source["TIME_SERIES_CODE"].str.split(".").str[8])
    if len(scopes[["REPORTING_COUNTRY", "DATE", "AGG_CODE"]].drop_duplicates()) != 1:
        raise ValueError("One submission must have exactly one country/period/aggregation scope.")
    if scopes["REPORTING_COUNTRY"].isna().any():
        raise ValueError("Invalid reporting-country security anchor.")
    states = source["BATCH_STATUS"].unique().tolist()
    if len(states) != 1 or states[0] not in ("PUBLISHED", "QUARANTINE"):
        raise ValueError("The submission verdict must be uniformly PUBLISHED or QUARANTINE.")
    expected_quality = "PASS" if states[0] == "PUBLISHED" else "FAIL"
    if not source["QUALITY_STATUS"].eq(expected_quality).all():
        raise ValueError("Quality and publication verdicts disagree.")
    source["OBS_VALUE"] = source["OBS_VALUE"].map(decimal_value)
    for name in PAYLOAD_COLUMNS:
        if name not in source:
            source[name] = None
    source["SUBMISSION_ID"] = context.submission_id
    source["SOURCE_SHA256"] = context.source_sha256
    source["SUBMITTED_AT"] = context.submitted_at
    source["RECEIVED_AT"] = context.received_at
    source["VALID_FROM"] = context.received_at
    source["VALID_TO"] = None if states[0] == "PUBLISHED" else context.received_at
    source["IS_CURRENT"] = states[0] == "PUBLISHED"
    source["RECORD_ID"] = [stable_hash([context.submission_id] + [row[name] for name in key]) for row in source.to_dict("records")]
    source["version_hash"] = [stable_hash([decimal_text(row[name]) if name == "OBS_VALUE" else row[name] for name in PAYLOAD_COLUMNS]) for row in source.to_dict("records")]
    return source[HISTORY_COLUMNS + (["BANK_CODE"] if "BANK_CODE" in source else [])]


def scope_mask(target, incoming):
    row = incoming.iloc[0]
    country = row["TIME_SERIES_CODE"].split(".")[8]
    return (target["TIME_SERIES_CODE"].str.split(".").str[8].eq(country)
            & target["DATE"].eq(row["DATE"]) & target["AGG_CODE"].eq(row["AGG_CODE"]))


def stage_transition(target, incoming):
    if target.empty:
        return incoming.assign(_operation="INSERT")
    missing = set(HISTORY_COLUMNS) - set(target)
    if missing:
        raise ValueError("Legacy history requires an explicit migration; missing " + ",".join(sorted(missing)))
    if target["RECORD_ID"].duplicated().any():
        raise ValueError("Existing history has duplicate record identities.")
    prior = target[target["SUBMISSION_ID"].eq(incoming.iloc[0]["SUBMISSION_ID"])]
    if not prior.empty:
        previous = set(zip(prior["RECORD_ID"], prior["SOURCE_SHA256"], prior["version_hash"]))
        proposed = set(zip(incoming["RECORD_ID"], incoming["SOURCE_SHA256"], incoming["version_hash"]))
        if previous != proposed:
            raise ValueError("Submission identity reused with different content or validation.")
        return incoming.iloc[:0].assign(_operation="INSERT")
    in_scope = target[scope_mask(target, incoming)]
    current = in_scope[in_scope["IS_CURRENT"].eq(True)]
    natural_key = NATURAL_KEY + (["BANK_CODE"] if "BANK_CODE" in target else [])
    if current.duplicated(natural_key).any():
        raise ValueError("Existing history has duplicate current observations.")
    inserts = incoming.assign(_operation="INSERT")
    if not incoming["IS_CURRENT"].all():
        return inserts
    accepted = in_scope[in_scope["BATCH_STATUS"].eq("PUBLISHED")]
    if not accepted.empty and incoming.iloc[0]["SUBMITTED_AT"] < accepted["SUBMITTED_AT"].max():
        inserts["IS_CURRENT"] = False
        inserts["VALID_TO"] = inserts["VALID_FROM"]
        return inserts
    closes = current.assign(
        IS_CURRENT=False, VALID_TO=incoming.iloc[0]["RECEIVED_AT"], _operation="CLOSE"
    )
    return pd.concat([closes, inserts], ignore_index=True)


def arrow_history(frame, *, operations=False):
    frame = frame.copy()
    frame.attrs = {}
    fields = [pa.field(name, pa.string()) for name in STRING_COLUMNS]
    fields.append(pa.field("OBS_VALUE", pa.decimal128(38, 3)))
    fields.extend(pa.field(name, pa.timestamp("us", tz="UTC")) for name in TIME_COLUMNS)
    fields.append(pa.field("IS_CURRENT", pa.bool_()))
    if "BANK_CODE" in frame:
        fields.append(pa.field("BANK_CODE", pa.string()))
    if operations:
        fields.append(pa.field("_operation", pa.string()))
    return pa.Table.from_pandas(frame, schema=pa.schema(fields), preserve_index=False)


def merge_local_submission(table_path, frame, context, *, before_commit=None):
    """Commit closes and inserts together; cooperating local writers share a file lock."""
    prepared = prepare_submission(frame, context)
    path = Path(table_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=30):
        if not (path / "_delta_log").exists():
            if before_commit:
                before_commit()
            write_deltalake(str(path), arrow_history(prepared), mode="error")
            return len(prepared)
        target = DeltaTable(str(path))
        staged = stage_transition(target.to_pandas(), prepared)
        if staged.empty:
            return 0
        if before_commit:
            before_commit()
        columns = prepared.columns.tolist()
        target.merge(
            source=arrow_history(staged, operations=True),
            predicate="target.RECORD_ID = source.RECORD_ID", source_alias="source", target_alias="target",
        ).when_matched_update(
            predicate="source._operation = 'CLOSE'",
            updates={"IS_CURRENT": "false", "VALID_TO": "source.VALID_TO"},
        ).when_not_matched_insert(
            predicate="source._operation = 'INSERT'",
            updates={name: f"source.{name}" for name in columns},
        ).execute()
        return len(prepared)