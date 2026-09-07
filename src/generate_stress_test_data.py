"""High-volume synthetic generator for scale and stress testing.

Distinct from ``generate_sovereign_submissions.py``, which produces a small,
hand-tuned corpus whose reconciliation arithmetic is deliberately exact so the
validation rules can be reasoned about. This module produces *volume*: a
combinatorial sweep of the 11 BIS_LBS dimensions across many jurisdictions,
sized to put the SCD2 merge, the row filter and the column mask under memory
and I/O pressure.

Nothing here is a deployment target and nothing here reaches a network. Every
value is drawn from a seeded generator, so a given ``seed`` reproduces a byte
-identical corpus on any machine - a benchmark whose input changes between runs
measures nothing.

**Multi-frequency by construction.** Segment 1 of ``TIME_SERIES_CODE`` is
``FREQ``. Locational Banking Statistics is collected quarterly, but the engine
is not quarterly: an international statistical body receives annual (``A``),
semi-annual (``S``), quarterly (``Q``) and monthly (``M``) aggregations from
different collections. The generator emits reporting periods in the correct
shape for each cadence, so the merge key and the portal filters are exercised
against a genuinely mixed-cadence history rather than a quarterly one.

Confidentiality is injected by *proportion of series*, not per row. A
confidential position stays confidential across its revisions, which is what
makes the column mask worth testing: a flag that flickers per row would let a
broken mask pass by accident on the rows that happened to be free.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# =====================================================================
# DIMENSION UNIVERSE
# =====================================================================

#: The 11 BIS_LBS dimensions in TIME_SERIES_CODE order. Segment 9 (L_REP_CTY)
#: is the sovereignty anchor the row filter and column mask both read.
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

#: Reporting jurisdictions. Only CA and US have persona groups in the reference
#: deployment; the rest exist so a cross-border leak has somewhere to leak *to*.
#: A single-jurisdiction corpus cannot detect the defect class this repo exists
#: to prevent, and a two-jurisdiction one barely can.
REPORTING_COUNTRIES: Tuple[str, ...] = ("CA", "US", "CH", "GB", "DE", "JP", "FR")

#: Counterparty sectors. B/M/F/C/G/H are reported institutional breakdowns;
#: A/N/U are the standard BIS aggregate codes the consistency checks reconcile
#: against.
COUNTERPART_SECTORS: Tuple[str, ...] = ("B", "M", "F", "C", "G", "H", "A", "N", "U")

COUNTERPART_COUNTRIES: Tuple[str, ...] = ("5J", "US", "GB", "DE", "JP", "FR", "CH", "CA", "1C")
CURRENCIES: Tuple[str, ...] = ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "TO1")
CURRENCY_TYPES: Tuple[str, ...] = ("D", "F", "U")
POSITIONS: Tuple[str, ...] = ("C", "L")
INSTRUMENTS: Tuple[str, ...] = ("A", "B", "G")
PARENT_COUNTRIES: Tuple[str, ...] = ("5J", "US", "GB", "DE", "CA")
BANK_TYPES: Tuple[str, ...] = ("A", "D", "F")
MEASURES: Tuple[str, ...] = ("S",)

#: Reporting cadences. LBS itself is quarterly; the platform is not.
FREQUENCIES: Tuple[str, ...] = ("A", "S", "Q", "M")

#: Confidentiality flags. 'F' is free to publish, 'C' is confidential and 'N'
#: is not for publication. Only C and N are masked.
CONFIDENTIAL_FLAGS: Tuple[str, ...] = ("C", "N")

DEFAULT_AGG_CODE = "LBSR"


def reporting_periods(freq: str, count: int, start_year: int = 2024) -> List[str]:
    """Builds reporting-period labels in the shape each cadence actually uses.

    A monthly series labelled ``2026-Q1`` would sort and group correctly by
    accident while being wrong, so each cadence gets its own label form.
    """
    periods: List[str] = []
    year = start_year
    index = 0
    per_year = {"A": 1, "S": 2, "Q": 4, "M": 12}[freq]

    while len(periods) < count:
        slot = index % per_year
        year = start_year + (index // per_year)
        if freq == "A":
            periods.append(f"{year}")
        elif freq == "S":
            periods.append(f"{year}-S{slot + 1}")
        elif freq == "Q":
            periods.append(f"{year}-Q{slot + 1}")
        else:
            periods.append(f"{year}-{slot + 1:02d}")
        index += 1
    return periods


@dataclass
class StressCorpusSpec:
    """Declarative description of the corpus to build.

    Attributes:
        target_rows: Row count to aim for. The generator widens the dimension
            sweep until it can meet this, then truncates deterministically.
        countries: Reporting jurisdictions to spread series across.
        frequencies: Cadences to emit. Multiple cadences share one history
            table, exactly as a real hub's do.
        periods_per_series: Reporting periods per series, before revisions.
        confidential_share: Proportion of *series* (not rows) flagged C or N.
        revision_share: Proportion of series that receive a second, revised
            observation, exercising the SCD2 close-and-insert path.
        quarantine_share: Proportion of revisions that arrive as QUARANTINE and
            must not disturb the published version.
        seed: Reproducibility anchor.
    """

    target_rows: int = 100_000
    countries: Sequence[str] = REPORTING_COUNTRIES
    frequencies: Sequence[str] = ("Q",)
    periods_per_series: int = 4
    confidential_share: float = 0.25
    revision_share: float = 0.20
    quarantine_share: float = 0.30
    agg_code: str = DEFAULT_AGG_CODE
    seed: int = 20260101

    def __post_init__(self) -> None:
        if self.target_rows < 1:
            raise ValueError("target_rows must be at least 1.")
        if not self.countries:
            raise ValueError("At least one reporting country is required.")
        for name in ("confidential_share", "revision_share", "quarantine_share"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0, got {value}.")
        unknown = set(self.frequencies) - set(FREQUENCIES)
        if unknown:
            raise ValueError(f"Unsupported frequencies {sorted(unknown)}; expected {FREQUENCIES}.")


def _series_keys(spec: StressCorpusSpec, needed: int, rng: np.random.Generator) -> List[str]:
    """Draws distinct 11-segment keys, spread evenly across jurisdictions.

    Sampling rather than a full cross-product: the complete sweep is millions of
    combinations, and materialising it to take a slice would defeat the point of
    a memory-pressure fixture.
    """
    keys: List[str] = []
    seen: set = set()
    countries = list(spec.countries)
    frequencies = list(spec.frequencies)

    # A generous ceiling on attempts; the dimension space is far larger than any
    # realistic `needed`, so exhaustion means the spec asked for more distinct
    # series than the universe holds.
    max_attempts = needed * 20
    attempts = 0

    while len(keys) < needed and attempts < max_attempts:
        attempts += 1
        parts = {
            "FREQ": frequencies[len(keys) % len(frequencies)],
            "L_MEASURE": MEASURES[0],
            "L_POSITION": POSITIONS[rng.integers(len(POSITIONS))],
            "L_INSTR": INSTRUMENTS[rng.integers(len(INSTRUMENTS))],
            "L_DENOM": CURRENCIES[rng.integers(len(CURRENCIES))],
            "L_CURR_TYPE": CURRENCY_TYPES[rng.integers(len(CURRENCY_TYPES))],
            "L_PARENT_CTY": PARENT_COUNTRIES[rng.integers(len(PARENT_COUNTRIES))],
            "L_REP_BANK_TYPE": BANK_TYPES[rng.integers(len(BANK_TYPES))],
            # Round-robin so every jurisdiction is represented even when the
            # requested series count is small.
            "L_REP_CTY": countries[len(keys) % len(countries)],
            "L_CP_SECTOR": COUNTERPART_SECTORS[rng.integers(len(COUNTERPART_SECTORS))],
            "L_CP_COUNTRY": COUNTERPART_COUNTRIES[rng.integers(len(COUNTERPART_COUNTRIES))],
        }
        key = ".".join(parts[dim] for dim in DSD_DIMENSIONS)
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)

    if len(keys) < needed:
        raise ValueError(
            f"Could only build {len(keys)} distinct series from the configured dimension "
            f"universe; {needed} were requested. Widen `countries` or the code lists."
        )
    return keys


def generate_macro_corpus(spec: Optional[StressCorpusSpec] = None) -> pd.DataFrame:
    """Builds a macro history frame shaped like ``agg_sdmx_history``.

    Returns:
        A DataFrame carrying TIME_SERIES_CODE, DATE, AGG_CODE, OBS_VALUE,
        OBS_STATUS, OBS_CONF, QUALITY_STATUS, FAILED_RULE_ID, BATCH_STATUS and
        the SCD2 columns VALID_FROM / VALID_TO / IS_CURRENT.
    """
    spec = spec or StressCorpusSpec()
    rng = np.random.default_rng(spec.seed)

    series_needed = max(1, spec.target_rows // max(1, spec.periods_per_series))
    keys = _series_keys(spec, series_needed, rng)

    # Confidentiality is fixed per series so a revision cannot silently flip a
    # masked value into a visible one.
    conf_count = int(len(keys) * spec.confidential_share)
    conf_assignment: Dict[str, str] = {}
    for position, key in enumerate(keys):
        if position < conf_count:
            conf_assignment[key] = CONFIDENTIAL_FLAGS[position % len(CONFIDENTIAL_FLAGS)]
        else:
            conf_assignment[key] = "F"

    period_cache = {
        freq: reporting_periods(freq, spec.periods_per_series) for freq in spec.frequencies
    }

    records: List[Dict[str, object]] = []
    revision_cutoff = int(len(keys) * spec.revision_share)

    for position, key in enumerate(keys):
        freq = key.split(".")[0]
        period_indices: Dict[str, int] = {}

        for period in period_cache[freq]:
            period_indices[period] = len(records)
            records.append(
                {
                    "TIME_SERIES_CODE": key,
                    "DATE": period,
                    "AGG_CODE": spec.agg_code,
                    "OBS_VALUE": float(np.round(rng.normal(5.0e8, 2.0e8), 2)),
                    "OBS_STATUS": "A",
                    "OBS_CONF": conf_assignment[key],
                    "QUALITY_STATUS": "PASS",
                    "FAILED_RULE_ID": None,
                    "BATCH_STATUS": "PUBLISHED",
                    "IS_CURRENT": True,
                }
            )

        if position < revision_cutoff:
            revised_period = period_cache[freq][-1]
            quarantined = (position % 100) < int(spec.quarantine_share * 100)

            # SCD2, not append-only. A *published* revision closes the version it
            # supersedes, so the key keeps exactly one open interval. A
            # *quarantined* revision closes only itself and leaves the published
            # figure live - that is the difference between stale data and
            # missing data, and it is the whole point of the quarantine path.
            if not quarantined:
                records[period_indices[revised_period]]["IS_CURRENT"] = False

            records.append(
                {
                    "TIME_SERIES_CODE": key,
                    "DATE": revised_period,
                    "AGG_CODE": spec.agg_code,
                    "OBS_VALUE": float(np.round(rng.normal(5.0e8, 2.0e8), 2)),
                    "OBS_STATUS": "A",
                    "OBS_CONF": conf_assignment[key],
                    "QUALITY_STATUS": "FAIL" if quarantined else "PASS",
                    "FAILED_RULE_ID": "LBS_CC01" if quarantined else None,
                    "BATCH_STATUS": "QUARANTINE" if quarantined else "PUBLISHED",
                    "IS_CURRENT": not quarantined,
                }
            )

    frame = pd.DataFrame.from_records(records)

    now = pd.Timestamp.now(tz="UTC")
    frame["VALID_FROM"] = now
    frame["VALID_TO"] = pd.Timestamp("9999-12-31 00:00:00", tz="UTC")
    frame.loc[~frame["IS_CURRENT"], "VALID_TO"] = now

    return frame.head(spec.target_rows).reset_index(drop=True)


def generate_micro_corpus(spec: Optional[StressCorpusSpec] = None, banks_per_series: int = 3) -> pd.DataFrame:
    """Builds a bank-level ledger that aggregates to the macro corpus grain."""
    spec = spec or StressCorpusSpec()
    macro = generate_macro_corpus(spec)
    rng = np.random.default_rng(spec.seed + 1)

    rows: List[Dict[str, object]] = []
    for record in macro.itertuples(index=False):
        share = rng.dirichlet(np.ones(banks_per_series))
        country = record.TIME_SERIES_CODE.split(".")[8]
        for bank_index in range(banks_per_series):
            rows.append(
                {
                    "TIME_SERIES_CODE": record.TIME_SERIES_CODE,
                    "BANK_CODE": f"BANK_{country}_{bank_index + 1}",
                    "DATE": record.DATE,
                    "AGG_CODE": record.AGG_CODE,
                    "OBS_VALUE": float(np.round(record.OBS_VALUE * share[bank_index], 2)),
                }
            )
    return pd.DataFrame.from_records(rows)


def summarise(frame: pd.DataFrame) -> Dict[str, object]:
    """Corpus shape, for asserting a benchmark actually exercised what it claims."""
    keys = frame["TIME_SERIES_CODE"].astype(str)
    return {
        "rows": int(len(frame)),
        "series": int(keys.nunique()),
        "jurisdictions": sorted(keys.str.split(".").str[8].unique().tolist()),
        "frequencies": sorted(keys.str.split(".").str[0].unique().tolist()),
        "confidential_rows": int(frame["OBS_CONF"].isin(CONFIDENTIAL_FLAGS).sum()),
        "quarantined_rows": int((frame["BATCH_STATUS"] != "PUBLISHED").sum()),
        "periods": int(frame["DATE"].nunique()),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rows", type=int, default=100_000, help="Target macro row count.")
    parser.add_argument(
        "--frequencies",
        default="Q",
        help="Comma-separated cadences to emit from A,S,Q,M (e.g. 'A,S,Q,M').",
    )
    parser.add_argument("--periods", type=int, default=4, help="Reporting periods per series.")
    parser.add_argument("--confidential-share", type=float, default=0.25)
    parser.add_argument("--revision-share", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--micro", action="store_true", help="Emit the bank-level ledger instead.")
    parser.add_argument("--out", default="", help="Write CSV here instead of printing a summary.")
    args = parser.parse_args(argv)

    spec = StressCorpusSpec(
        target_rows=args.rows,
        frequencies=tuple(f.strip().upper() for f in args.frequencies.split(",") if f.strip()),
        periods_per_series=args.periods,
        confidential_share=args.confidential_share,
        revision_share=args.revision_share,
        seed=args.seed,
    )

    frame = generate_micro_corpus(spec) if args.micro else generate_macro_corpus(spec)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        frame.to_csv(args.out, index=False)
        print(f"Wrote {len(frame):,} rows to {args.out}")
    else:
        for name, value in summarise(frame).items() if not args.micro else [("rows", len(frame))]:
            print(f"{name:>18}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
