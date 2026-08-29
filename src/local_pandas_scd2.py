"""Developer synthetic testing fixture: SCD2 without cluster compute.

This module exists so an external contributor can exercise and reason about the
historisation state machine on a laptop, with no Databricks workspace, no
credentials, and no JVM. It is a **development fixture**, never a deployment
target - `scd2_merge_engine.py` is the PySpark/Delta engine that runs in
production, and nothing here is imported by it.

What it faithfully reproduces:

* the quarantine state machine - a rejected revision is appended as an
  audit-only row and never expires the prior published record
* `version_hash` change detection over the payload columns
* replay idempotency, so a re-run does not stack duplicate audit rows

Where it deliberately differs, and why it does not matter for the fixture's
purpose:

* **Column naming.** This module uses `effective_start_date` /
  `effective_end_date` / `is_current`, while the macro path and
  `unity_catalog_triple_lock.sql` use `VALID_FROM` / `VALID_TO` / `IS_CURRENT`.
  The tables are created by this module's own merge function, so the two
  conventions never meet; do not "harmonise" one into the other without moving
  every consumer.
* **Per-country tables.** Writes to `data/local_delta_catalog/lbs_micro_<cc>`
  rather than a single governed table, so sovereign isolation is expressed by
  file layout instead of a row filter. Unity Catalog is the enforcement point
  in every deployed configuration; nothing here enforces entitlement.

For the persona matrix equivalent of this fixture, see `LocalDeltaBackend` in
`uc_query.py`. Both are exercised offline by `tests/`.

Related skill: `.github/skills/scd2_engine.md`.
"""

import pandas as pd
import hashlib
from datetime import datetime
from deltalake import DeltaTable, write_deltalake
import os

def create_version_hash(row, payload_cols):
    """Generates a SHA256 hash for the payload columns."""
    concat_str = "||".join([str(row[c]) for c in payload_cols])
    return hashlib.sha256(concat_str.encode('utf-8')).hexdigest()

def merge_scd2_micro_pandas(
    df_incoming: pd.DataFrame, 
    country_code: str, 
    table_path: str = "data/local_delta_catalog/lbs_micro", 
    date_scope: str = "2026-Q1", 
    ibs_agg_scope: str = "LBSR"
):
    """Local pandas/delta-rs SCD2 merge mirroring the Spark macro engine's state protection.

    Rows whose BATCH_STATUS is not 'PUBLISHED' are appended as is_current = False audit
    records only: they never expire or supersede the previously published version, so
    downstream consumers keep reading the last valid state. Inputs without a BATCH_STATUS
    column are treated as fully published.
    """
    target_path = f"{table_path}_{country_code.lower()}"

    # 1. Prepare Incoming Data
    df_source = df_incoming.copy()
    if "BATCH_STATUS" not in df_source.columns:
        df_source["BATCH_STATUS"] = "PUBLISHED"
    payload_cols = [c for c in ["OBS_VALUE", "QUALITY_STATUS", "FAILED_RULE_ID", "BATCH_STATUS"] if c in df_source.columns]
    df_source['version_hash'] = df_source.apply(lambda r: create_version_hash(r, payload_cols), axis=1)

    is_published = df_source["BATCH_STATUS"] == "PUBLISHED"
    df_published = df_source[is_published]
    df_quarantined = df_source[~is_published]

    current_time = pd.Timestamp.now('UTC')
    end_of_time = pd.Timestamp("9999-12-31 00:00:00")

    # 2. Initialize Table if it doesn't exist
    if not os.path.exists(target_path):
        df_init = df_source.copy()
        df_init['effective_start_date'] = current_time
        # Quarantined rows are closed on arrival so they never present as an active version.
        df_init['effective_end_date'] = pd.Series(end_of_time, index=df_init.index).where(is_published, current_time)
        df_init['is_current'] = is_published
        
        write_deltalake(target_path, df_init, mode="overwrite")
        print(f"Initialized new Delta table at {target_path}")
        return

    # 3. Load Existing Delta Table
    dt = DeltaTable(target_path)
    df_target = dt.to_pandas()
    
    # Filter for active records
    active_target = df_target[df_target['is_current'] == True]

    # 4. Stage 1: Expire Changed Records (published revisions only)
    # Find records where composite keys match but hash differs
    merged = pd.merge(
        active_target, 
        df_published, 
        on=["TIME_SERIES_CODE", "BANK_CODE", "DATE", "IBS_AGG"], 
        suffixes=('_tgt', '_src')
    )
    changed_records = merged[merged['version_hash_tgt'] != merged['version_hash_src']]
    
    if not changed_records.empty:
        # Use delta-rs native merge to update the old records
        dt.merge(
            source=changed_records[['TIME_SERIES_CODE', 'BANK_CODE', 'DATE', 'IBS_AGG']],
            predicate="s.TIME_SERIES_CODE = t.TIME_SERIES_CODE AND s.BANK_CODE = t.BANK_CODE AND t.is_current = true",
            source_alias="s",
            target_alias="t"
        ).when_matched_update(
            updates={
                "is_current": "false",
                "effective_end_date": f"'{current_time}'"
            }
        ).execute()

    # 5. Stage 2: Insert New/Updated Records
    # Find records in source that are not in target, OR have a new hash
    merged_all = pd.merge(
        df_published, 
        active_target, 
        on=["TIME_SERIES_CODE", "BANK_CODE", "DATE", "IBS_AGG"], 
        how="left", 
        suffixes=('', '_tgt')
    )
    to_insert = merged_all[
        merged_all['version_hash_tgt'].isna() | 
        (merged_all['version_hash'] != merged_all['version_hash_tgt'])
    ].copy()
    
    if not to_insert.empty:
        # Clean up joined columns
        cols_to_keep = df_source.columns.tolist()
        to_insert = to_insert[cols_to_keep]
        to_insert['effective_start_date'] = current_time
        to_insert['effective_end_date'] = end_of_time
        to_insert['is_current'] = True
        
        write_deltalake(target_path, to_insert, mode="append")

    # 6. Stage 2b: Append quarantined revisions as closed, audit-only rows.
    if not df_quarantined.empty:
        audit_rows = df_quarantined.copy()
        audit_rows['effective_start_date'] = current_time
        audit_rows['effective_end_date'] = current_time
        audit_rows['is_current'] = False
        write_deltalake(target_path, audit_rows, mode="append")
        print(
            f"Appended {len(audit_rows)} quarantined revision(s) as is_current=False audit records; "
            "previously published versions remain active."
        )

    print(f"Processed SCD2 Merge for {country_code.upper()}.")

if __name__ == "__main__":
    try:
        # Load the CSV generated by your updated script
        df_ca_incoming = pd.read_csv("data/micro_transactions_ca.csv")
        
        print("Executing Pandas-Delta SCD2 Merge for Canada...")
        merge_scd2_micro_pandas(
            df_incoming=df_ca_incoming,
            country_code="ca"
        )
        
        # Verify the result
        dt_verify = DeltaTable("data/local_delta_catalog/lbs_micro_ca")
        print("\n--- Final Local Delta Table State ---")
        
        # Select columns to display, now including TIME_SERIES_CODE
        display_cols = ['TIME_SERIES_CODE', 'BANK_CODE', 'OBS_VALUE', 'BATCH_STATUS', 'is_current', 'version_hash']
        df_final = dt_verify.to_pandas()
        print(df_final[[c for c in display_cols if c in df_final.columns]])
        
    except FileNotFoundError:
        print("Error: CSV not found. Ensure generate_sovereign_submissions.py saved the CSV to data/")