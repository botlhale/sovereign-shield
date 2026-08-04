"""Dynamic SDMx 3.0 rule validation engine for BIS Locational Banking Statistics.

`SDMxRuleValidator` ingests sovereign SDMx 3.0 XML (ML) submission files
(written by `generate_sovereign_submissions.py`) using `pysdmx`, dynamically
parses the mathematical consistency checks defined in
`docs/reference_standards/checks_lbs.xls` (Sheet: `LBS`), and executes those
checks against each country's aggregated macro time series.

Failing observations are never dropped: every row is tagged with
`QUALITY_STATUS` and, on failure, a comma-separated `FAILED_RULE_ID` list.
The "Quarterly Quarantine" mechanism then flags a country's *entire*
reporting-quarter batch as `QUARANTINED` if any of its rows failed, or
`PUBLISHED` if the whole batch is clean.
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import pysdmx.io as sdmx_io
from pysdmx.model.dataflow import DataStructureDefinition, Role

# =====================================================================
# CONFIGURATION & CONSTANTS
# =====================================================================

#: Path to the dynamic rule source (BIS consistency checks workbook).
CHECKS_XLS_PATH: str = os.path.join("docs", "reference_standards", "checks_lbs.xls")

#: Sheet within `checks_lbs.xls` containing the LBS consistency checks.
CHECKS_SHEET_NAME: str = "LBS"

#: Live BIS REST endpoint exposing the BIS_LBS Data Structure Definition (DSD).
BIS_LBS_DSD_URL: str = "https://stats.bis.org/api/v1/datastructure/BIS/BIS_LBS/latest?references=all"

#: Directory containing sovereign SDMx 3.0 XML submission files.
DATA_DIR: str = "data"

#: Aggregation framework code. Not modeled as a DSD dimension/attribute, so it
#: is reattached as a constant when ingesting SDMx-ML submissions.
IBS_AGG_CODE: str = "LBSR"

#: Fallback 11 BIS_LBS dimensions, used only if the live DSD cannot be fetched.
FALLBACK_DSD_DIMENSIONS: List[str] = [
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

#: Non-dimension columns present in the parsed rules workbook.
_RULE_METADATA_COLUMNS = {"Check No", "Description", "Dimensions1", "Aggregate_to_check1", "Calculation"}

#: Placeholder code meaning "match any value for this dimension" (e.g. the
#: reporting country's own domestic currency or residency country).
WILDCARD_CODE: str = "ISO"

#: Cells that represent "no value" / a truncated list (e.g. "..", "…").
_EMPTY_TOKEN_RE = re.compile(r"^[.\u2026\s]*$")

#: A footnote is a trailing digit appended to a single-letter code (e.g. "U2" -> "U").
#: Multi-letter codes that end in digits (e.g. "TO1", "UN9") are real codes, not footnotes.
_FOOTNOTE_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

#: Numerical tolerance used when comparing an aggregate against its components.
EQUALITY_TOLERANCE: float = 1e-4


@dataclass
class LbsRule:
    """A single dynamically parsed consistency check from `checks_lbs.xls`."""

    check_no: str
    description: str
    dim_names: List[str]
    aggregate: Dict[str, str]
    components: List[Dict[str, str]]


class SDMxRuleValidator:
    """Dynamically parses BIS LBS consistency checks and validates SDMx 3.0 submissions.

    The validator lazily fetches the live BIS_LBS Data Structure Definition
    (DSD) to determine the authoritative dimension order, lazily parses the
    `checks_lbs.xls` consistency rules, ingests sovereign SDMx 3.0 XML
    submission files into macro DataFrames, and evaluates every parsed rule
    against those DataFrames without dropping any observation.
    """

    def __init__(
        self,
        rules_path: str = CHECKS_XLS_PATH,
        sheet_name: str = CHECKS_SHEET_NAME,
        dsd_url: str = BIS_LBS_DSD_URL,
    ) -> None:
        """Initializes the validator with the rule source and live DSD endpoint.

        Args:
            rules_path: Path to the `checks_lbs.xls` workbook.
            sheet_name: Sheet within the workbook containing the LBS checks.
            dsd_url: SDMx REST endpoint returning the live BIS_LBS DSD.
        """
        self.rules_path = rules_path
        self.sheet_name = sheet_name
        self.dsd_url = dsd_url
        self._dsd: Optional[DataStructureDefinition] = None
        self._dimension_order: Optional[List[str]] = None
        self._rules: Optional[List[LbsRule]] = None

    @property
    def dsd(self) -> DataStructureDefinition:
        """Lazily fetches and caches the live BIS_LBS DSD from the BIS REST API."""
        if self._dsd is None:
            message = sdmx_io.read_sdmx(self.dsd_url, validate=False)
            dsds = message.get_data_structure_definitions()
            if not dsds:
                raise ValueError(f"No DataStructureDefinition found at '{self.dsd_url}'.")
            self._dsd = dsds[0]
        return self._dsd

    @property
    def dimension_order(self) -> List[str]:
        """The ordered list of the 11 BIS_LBS dimensions, derived from the live DSD.

        Falls back to `FALLBACK_DSD_DIMENSIONS` if the live DSD cannot be fetched.
        """
        if self._dimension_order is None:
            try:
                self._dimension_order = [
                    component.id
                    for component in self.dsd.components
                    if component.role == Role.DIMENSION and component.id != "TIME_PERIOD"
                ]
            except Exception as exc:  # noqa: BLE001 - network/parse failures are non-fatal here.
                print(f"Warning: could not fetch live BIS_LBS DSD ({exc}). Falling back to known dimension order.")
                self._dimension_order = list(FALLBACK_DSD_DIMENSIONS)
        return self._dimension_order

    @property
    def rules(self) -> List[LbsRule]:
        """Lazily parses and caches the consistency checks from `checks_lbs.xls`."""
        if self._rules is None:
            self._rules = self._parse_rules()
        return self._rules

    # =================================================================
    # Dynamic Excel rule parsing
    # =================================================================

    def _find_header_row(self, max_scan: int = 20) -> int:
        """Scans the top of the sheet to dynamically locate the `Check No` header row.

        Args:
            max_scan: Maximum number of leading rows to inspect.

        Returns:
            The 0-based row index to use as the pandas header row.

        Raises:
            ValueError: If no row contains a `Check No` cell within `max_scan` rows.
        """
        preview = pd.read_excel(self.rules_path, sheet_name=self.sheet_name, header=None, nrows=max_scan)
        for row_idx in range(len(preview)):
            row_values = preview.iloc[row_idx].astype(str).str.strip()
            if (row_values == "Check No").any():
                return row_idx
        raise ValueError(f"Could not locate a 'Check No' header row in the first {max_scan} rows of '{self.rules_path}'.")

    def _parse_rules(self) -> List[LbsRule]:
        """Reads `checks_lbs.xls`, skips metadata rows, and parses every consistency check.

        Returns:
            A list of `LbsRule` objects. Rules whose aggregate or every
            component cannot be resolved to the current dimension order are
            skipped (e.g. section header rows, or checks with malformed cells).
        """
        header_row = self._find_header_row()
        df_rules = pd.read_excel(self.rules_path, sheet_name=self.sheet_name, header=header_row)

        # Drop section-header and blank rows: only genuine checks have a `Check No`.
        df_rules = df_rules[df_rules["Check No"].notna()].reset_index(drop=True)

        component_columns = [c for c in df_rules.columns if c not in _RULE_METADATA_COLUMNS]
        dim_names_all = self.dimension_order

        parsed_rules: List[LbsRule] = []
        for _, row in df_rules.iterrows():
            dim_names = self._parse_dimension_positions(row["Dimensions1"], dim_names_all)
            if not dim_names:
                continue

            aggregate = self._parse_code_cell(row["Aggregate_to_check1"], dim_names)
            if aggregate is None:
                continue

            components: List[Dict[str, str]] = []
            for col in component_columns:
                parsed = self._parse_code_cell(row.get(col), dim_names)
                if parsed is not None:
                    components.append(parsed)
            if not components:
                continue

            parsed_rules.append(
                LbsRule(
                    check_no=str(row["Check No"]).strip(),
                    description=str(row["Description"]).strip() if pd.notna(row["Description"]) else "",
                    dim_names=dim_names,
                    aggregate=aggregate,
                    components=components,
                )
            )
        return parsed_rules

    @staticmethod
    def _parse_dimension_positions(raw: object, dim_names_all: List[str]) -> List[str]:
        """Resolves a `Dimensions1` cell (e.g. `5 and 6`, `10`) into dimension names.

        Args:
            raw: The raw `Dimensions1` cell value (numeric or free text).
            dim_names_all: The full, ordered list of BIS_LBS dimension names.

        Returns:
            The dimension names at the 1-based positions referenced by `raw`.
        """
        if isinstance(raw, (int, float)) and not pd.isna(raw):
            positions = [int(raw)]
        elif isinstance(raw, str):
            positions = [int(n) for n in re.findall(r"\d+", raw)]
        else:
            return []
        return [dim_names_all[p - 1] for p in positions if 0 < p <= len(dim_names_all)]

    @staticmethod
    def _strip_footnote(code: str) -> str:
        """Strips a trailing footnote digit from a single-letter code (e.g. `U2` -> `U`).

        Multi-letter codes ending in digits (e.g. `TO1`, `UN9`) are real BIS
        codes and are returned unchanged.
        """
        match = _FOOTNOTE_RE.fullmatch(code)
        if match and len(match.group(1)) == 1:
            return match.group(1)
        return code

    @classmethod
    def _parse_code_cell(cls, raw: object, dim_names: List[str]) -> Optional[Dict[str, str]]:
        """Parses a colon-separated rule cell (e.g. `TO1:A`, `[ISO:D]`) into a dimension map.

        Args:
            raw: The raw cell value (e.g. `"UN9:U2"`, `"[ISO:D]"`, `"A"`, `".."`, `NaN`).
            dim_names: The dimension names the colon-separated parts map to, in order.

        Returns:
            A mapping of dimension name to footnote-stripped code, or `None` if
            the cell is empty, a placeholder token, or does not align with `dim_names`.
        """
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return None
        text = str(raw).strip().strip("[]").strip()
        if not text or _EMPTY_TOKEN_RE.match(text):
            return None
        parts = [part.strip() for part in text.split(":")]
        if len(parts) != len(dim_names):
            return None
        codes = [cls._strip_footnote(part) for part in parts]
        return dict(zip(dim_names, codes))

    # =================================================================
    # SDMx 3.0 XML ingestion
    # =================================================================

    def load_submission(self, xml_path: str) -> pd.DataFrame:
        """Ingests a single sovereign SDMx 3.0 XML submission into a macro DataFrame.

        Args:
            xml_path: Path to a structure-specific SDMx-ML 3.0 data file (e.g.
                `data/ca_submission_2026_Q1.xml`).

        Returns:
            A DataFrame with columns `TIME_SERIES_CODE`, `DATE`, `IBS_AGG`,
            `OBS_VALUE`, `OBS_STATUS`, and `OBS_CONF`.

        Raises:
            ValueError: If the SDMx message contains no dataset.
        """
        message = sdmx_io.read_sdmx(xml_path, validate=False)
        datasets = message.get_datasets()
        if not datasets:
            raise ValueError(f"No datasets found in SDMx message '{xml_path}'.")

        data = datasets[0].data.copy()
        dim_cols = [dim for dim in self.dimension_order if dim in data.columns]
        data["TIME_SERIES_CODE"] = data[dim_cols].astype(str).agg(".".join, axis=1)
        data = data.rename(columns={"TIME_PERIOD": "DATE"})
        data["OBS_VALUE"] = pd.to_numeric(data["OBS_VALUE"])
        data["IBS_AGG"] = IBS_AGG_CODE
        for col in ("OBS_STATUS", "OBS_CONF"):
            if col not in data.columns:
                data[col] = pd.NA

        return data[["TIME_SERIES_CODE", "DATE", "IBS_AGG", "OBS_VALUE", "OBS_STATUS", "OBS_CONF"]].reset_index(drop=True)

    def load_submissions(self, directory: str = DATA_DIR, pattern: str = "*_submission_*.xml") -> Dict[str, pd.DataFrame]:
        """Discovers and ingests every sovereign SDMx 3.0 XML file in `directory`.

        Args:
            directory: Directory to scan for submission files.
            pattern: Glob pattern identifying submission files, whose leading
                underscore-delimited token is treated as the country code
                (e.g. `ca_submission_2026_Q1.xml` -> `'ca'`).

        Returns:
            A dict keyed by lower-case country code, mapping to each
            country's ingested macro DataFrame.
        """
        submissions: Dict[str, pd.DataFrame] = {}
        for path in sorted(glob.glob(os.path.join(directory, pattern))):
            country_code = os.path.basename(path).split("_")[0].lower()
            submissions[country_code] = self.load_submission(path)
        return submissions

    # =================================================================
    # Validation & the Quarterly Quarantine
    # =================================================================

    def validate(self, df_macro: pd.DataFrame) -> pd.DataFrame:
        """Validates a macro DataFrame against every dynamically parsed LBS rule.

        Every `Aggregate_to_check1` (LHS) is compared against the sum of its
        reported components (RHS): `abs(LHS - sum(RHS)) < EQUALITY_TOLERANCE`.
        A check is skipped for a given series context when none of its
        components were actually reported (i.e. that breakdown is simply not
        part of the submission), rather than being treated as a failure.

        No row is ever dropped. Every row is tagged with `QUALITY_STATUS`
        (`'PASS'` or `'FAIL'`) and `FAILED_RULE_ID` (comma-separated `Check No`
        values). Finally, the entire reporting-quarter batch for a country is
        flagged `BATCH_STATUS = 'QUARANTINED'` if any row failed, or
        `'PUBLISHED'` if the whole batch is clean.

        Args:
            df_macro: A macro DataFrame with `TIME_SERIES_CODE`, `DATE`,
                `IBS_AGG`, and `OBS_VALUE` columns (as produced by `load_submission`).

        Returns:
            A DataFrame with columns `TIME_SERIES_CODE`, `DATE`, `IBS_AGG`,
            `OBS_VALUE`, `OBS_STATUS`, `OBS_CONF`, `QUALITY_STATUS`,
            `FAILED_RULE_ID`, and `BATCH_STATUS`.
        """
        df = df_macro.copy().reset_index(drop=True)

        dims_df = df["TIME_SERIES_CODE"].str.split(".", expand=True)
        if dims_df.shape[1] != len(self.dimension_order):
            raise ValueError(
                f"TIME_SERIES_CODE has {dims_df.shape[1]} segments; expected {len(self.dimension_order)} "
                f"({', '.join(self.dimension_order)})."
            )
        dims_df.columns = self.dimension_order
        df = pd.concat([df, dims_df], axis=1)

        df["QUALITY_STATUS"] = "PASS"
        df["FAILED_RULE_ID"] = ""

        for rule in self.rules:
            context_dims = [dim for dim in self.dimension_order if dim not in rule.dim_names]
            group_cols = context_dims + ["DATE", "IBS_AGG"]
            for _, group in df.groupby(group_cols, sort=False, dropna=False):
                agg_rows = self._filter_rows(group, rule.aggregate)
                if agg_rows.empty:
                    continue  # Aggregate series not reported in this context; not applicable.

                rhs_sum = 0.0
                rhs_reported = False
                for component in rule.components:
                    comp_rows = self._filter_rows(group, component)
                    if not comp_rows.empty:
                        rhs_reported = True
                        rhs_sum += comp_rows["OBS_VALUE"].sum()

                if not rhs_reported:
                    continue  # No breakdown reported for this check; not applicable.

                lhs_sum = agg_rows["OBS_VALUE"].sum()
                if abs(lhs_sum - rhs_sum) >= EQUALITY_TOLERANCE:
                    idx = agg_rows.index
                    df.loc[idx, "QUALITY_STATUS"] = "FAIL"
                    df.loc[idx, "FAILED_RULE_ID"] = df.loc[idx, "FAILED_RULE_ID"].apply(
                        lambda existing, rule_id=rule.check_no: f"{existing},{rule_id}" if existing else rule_id
                    )

        df["L_REP_CTY"] = df["TIME_SERIES_CODE"].str.split(".").str[self.dimension_order.index("L_REP_CTY")]
        batch_status = (
            df.groupby(["L_REP_CTY", "DATE"])["QUALITY_STATUS"]
            .apply(lambda statuses: "QUARANTINED" if (statuses == "FAIL").any() else "PUBLISHED")
            .rename("BATCH_STATUS")
            .reset_index()
        )
        df = df.merge(batch_status, on=["L_REP_CTY", "DATE"], how="left")

        return df[
            [
                "TIME_SERIES_CODE",
                "DATE",
                "IBS_AGG",
                "OBS_VALUE",
                "OBS_STATUS",
                "OBS_CONF",
                "QUALITY_STATUS",
                "FAILED_RULE_ID",
                "BATCH_STATUS",
            ]
        ]

    @staticmethod
    def _filter_rows(group: pd.DataFrame, code_map: Dict[str, str]) -> pd.DataFrame:
        """Filters `group` down to rows matching every non-wildcard dimension code in `code_map`."""
        mask = pd.Series(True, index=group.index)
        for dim_name, code in code_map.items():
            if code == WILDCARD_CODE:
                continue
            mask &= group[dim_name] == code
        return group[mask]


if __name__ == "__main__":
    validator = SDMxRuleValidator()
    print(f"Dynamically parsed {len(validator.rules)} consistency checks from '{validator.rules_path}'.")

    country_submissions = validator.load_submissions()
    if not country_submissions:
        raise SystemExit(f"No SDMx 3.0 XML submission files found in '{DATA_DIR}/'.")

    all_results: List[pd.DataFrame] = []
    for country_code, df_macro in country_submissions.items():
        print(f"\nValidating sovereign submission: {country_code.upper()} ({len(df_macro)} series)...")
        result = validator.validate(df_macro)
        result.insert(0, "SUBMITTING_COUNTRY", country_code.upper())
        all_results.append(result)

    combined = pd.concat(all_results, ignore_index=True)

    print("\n--- Combined Validation Summary ---")
    print(combined.to_string(index=False))

    print("\n--- Quarterly Quarantine Decision ---")
    batch_summary = combined.drop_duplicates(subset=["SUBMITTING_COUNTRY", "DATE"])[
        ["SUBMITTING_COUNTRY", "DATE", "BATCH_STATUS"]
    ].reset_index(drop=True)
    print(batch_summary.to_string(index=False))
