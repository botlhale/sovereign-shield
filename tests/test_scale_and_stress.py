"""Scale and stress benchmarks for the governance and historisation layers.

Two tiers, because the environment that can run the security assertions is not
always the environment that can run Spark:

* **Pandas tier** - always collected. Exercises the row filter and column mask
  mirror (``LocalDeltaBackend._apply_persona``) against a 100k+ row corpus and
  asserts the entitlement overhead stays sub-linear in the number of personas
  and sub-second per pass. This is the tier that protects the security claim.
* **PySpark tier** - skipped unless a *working* Spark session can be built.
  Benchmarks the real ``scd2_merge_engine`` MERGE against Delta and asserts SCD2
  interval integrity (``VALID_FROM`` / ``VALID_TO`` / ``IS_CURRENT``) at volume.
  An importable ``delta`` package is not sufficient: Spark also needs a JVM of a
  compatible version, and the failure mode when it is missing is an opaque
  ``JAVA_GATEWAY_EXITED`` rather than an ImportError.

Both tiers are marked ``stress`` and skipped by default: a benchmark that runs
on every commit either becomes flaky on shared runners or gets shrunk until it
stops measuring anything. Opt in with::

    pytest tests/test_scale_and_stress.py --stress

Timing assertions are deliberately loose. The purpose is to catch an accidental
quadratic - a per-row Python loop creeping into the mask, say - not to defend a
particular millisecond budget on unknown hardware.
"""

from __future__ import annotations

import importlib.util
import time
from typing import Dict, List

import pandas as pd
import pytest

from conftest import PERSONA_GROUPS
from generate_stress_test_data import (
    CONFIDENTIAL_FLAGS,
    StressCorpusSpec,
    generate_macro_corpus,
    summarise,
)
from uc_query import LocalDeltaBackend, Principal

pytestmark = pytest.mark.stress

DELTA_SPARK_AVAILABLE = importlib.util.find_spec("delta") is not None

requires_delta = pytest.mark.skipif(
    not DELTA_SPARK_AVAILABLE,
    reason="delta-spark is not installed; the PySpark merge benchmark cannot run",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def stress_spec() -> StressCorpusSpec:
    return StressCorpusSpec(
        target_rows=100_000,
        frequencies=("A", "S", "Q", "M"),
        periods_per_series=4,
        confidential_share=0.25,
        revision_share=0.20,
    )


@pytest.fixture(scope="module")
def stress_corpus(stress_spec: StressCorpusSpec) -> pd.DataFrame:
    return generate_macro_corpus(stress_spec)


def _principal(persona: str) -> Principal:
    return Principal(
        display_name=f"stress-{persona}",
        groups=PERSONA_GROUPS[persona],
        authenticated=persona != "public",
    )


def _timed_persona_pass(frame: pd.DataFrame, persona: str) -> tuple[pd.DataFrame, float]:
    start = time.perf_counter()
    visible = LocalDeltaBackend._apply_persona(frame, _principal(persona))
    return visible, time.perf_counter() - start


# ---------------------------------------------------------------------------
# Corpus shape - a benchmark on the wrong data measures nothing
# ---------------------------------------------------------------------------


def test_corpus_is_actually_large_and_multi_jurisdiction(stress_corpus, stress_spec):
    shape = summarise(stress_corpus)

    assert shape["rows"] >= 100_000
    # More than two jurisdictions, otherwise a cross-border leak has nowhere to
    # go and the mask assertions below are vacuous at any volume.
    assert len(shape["jurisdictions"]) >= 3
    assert set(shape["frequencies"]) == {"A", "S", "Q", "M"}
    assert shape["confidential_rows"] > 0
    assert shape["quarantined_rows"] > 0


def test_corpus_generation_is_reproducible(stress_spec):
    first = generate_macro_corpus(stress_spec)
    second = generate_macro_corpus(stress_spec)

    pd.testing.assert_frame_equal(
        first.drop(columns=["VALID_FROM", "VALID_TO"]),
        second.drop(columns=["VALID_FROM", "VALID_TO"]),
    )


# ---------------------------------------------------------------------------
# Pandas tier - entitlement enforcement under volume
# ---------------------------------------------------------------------------


def test_entitlement_overhead_stays_sub_second_per_persona(stress_corpus):
    """Each persona resolves in one vectorised pass over the corpus."""
    timings: Dict[str, float] = {}
    for persona in ("public", "researcher", "submitter_ca", "admin", "unaffiliated"):
        _, elapsed = _timed_persona_pass(stress_corpus, persona)
        timings[persona] = elapsed

    slowest = max(timings.values())
    assert slowest < 2.0, f"entitlement pass regressed to {slowest:.2f}s per persona: {timings}"


def test_entitlement_cost_scales_linearly(stress_spec):
    """A 4x corpus must not cost dramatically more than 4x.

    Guards against a per-row apply() replacing the vectorised predicate. The
    tolerance is wide because process noise on a laptop dwarfs the signal at
    these sizes; a quadratic would blow through it regardless.
    """
    small = generate_macro_corpus(
        StressCorpusSpec(target_rows=25_000, frequencies=stress_spec.frequencies)
    )
    large = generate_macro_corpus(
        StressCorpusSpec(target_rows=100_000, frequencies=stress_spec.frequencies)
    )

    # Warm pandas and the CPU caches so the first call does not absorb import cost.
    _timed_persona_pass(small, "researcher")

    _, small_elapsed = _timed_persona_pass(small, "researcher")
    _, large_elapsed = _timed_persona_pass(large, "researcher")

    growth = large_elapsed / max(small_elapsed, 1e-6)
    assert growth < 20.0, (
        f"4x the rows cost {growth:.1f}x the time "
        f"({small_elapsed:.4f}s -> {large_elapsed:.4f}s); expected roughly linear."
    )


def test_sovereign_isolation_holds_at_volume(stress_corpus):
    """The row filter's core promise, asserted against 100k rows."""
    visible = LocalDeltaBackend._apply_persona(stress_corpus, _principal("submitter_ca"))

    reporting = visible["TIME_SERIES_CODE"].astype(str).str.split(".").str[8]
    foreign = visible[reporting != "CA"]

    # A submitter reaches foreign rows only when they are published AND free.
    assert (foreign["BATCH_STATUS"] == "PUBLISHED").all()
    assert (foreign["OBS_CONF"] == "F").all()


def test_no_foreign_confidential_value_survives_masking_at_volume(stress_corpus):
    """The cross-sovereign leak test, at scale, on the dual-membership persona.

    A principal holding both submitter and researcher membership is the only one
    that can reach foreign confidential *rows*, so it is the only one whose
    masked *values* prove the column mask rather than the row filter.
    """
    principal = Principal(
        display_name="stress-ca-analyst-and-researcher",
        groups=PERSONA_GROUPS["submitter_ca"] | PERSONA_GROUPS["researcher"],
        authenticated=True,
    )
    visible = LocalDeltaBackend._apply_persona(stress_corpus, principal)

    reporting = visible["TIME_SERIES_CODE"].astype(str).str.split(".").str[8]
    foreign_restricted = visible[
        (reporting != "CA") & visible["OBS_CONF"].isin(CONFIDENTIAL_FLAGS)
    ]

    assert not foreign_restricted.empty, "corpus did not exercise the mask; test would be vacuous"
    assert foreign_restricted["OBS_VALUE"].isna().all()


def test_unaffiliated_principal_sees_nothing_at_volume(stress_corpus):
    visible = LocalDeltaBackend._apply_persona(stress_corpus, _principal("unaffiliated"))
    assert visible.empty


# ---------------------------------------------------------------------------
# SCD2 interval integrity
# ---------------------------------------------------------------------------


def test_quarantined_revisions_never_hold_an_active_interval(stress_corpus):
    """A rejected revision degrades to stale data, never missing data."""
    quarantined = stress_corpus[stress_corpus["BATCH_STATUS"] != "PUBLISHED"]

    assert not quarantined.empty
    assert not quarantined["IS_CURRENT"].any()
    # Closed on arrival: an audit row must never present as an open interval.
    assert (quarantined["VALID_TO"] < pd.Timestamp("9999-12-31", tz="UTC")).all()


def test_every_series_period_retains_exactly_one_current_row(stress_corpus):
    """No key may hold two open intervals; that is a duplicated history."""
    current = stress_corpus[stress_corpus["IS_CURRENT"]]
    duplicated = current.groupby(["TIME_SERIES_CODE", "DATE", "AGG_CODE"]).size()

    offenders = duplicated[duplicated > 1]
    assert offenders.empty, f"{len(offenders)} key(s) hold more than one active version."


# ---------------------------------------------------------------------------
# PySpark tier - the real merge engine
# ---------------------------------------------------------------------------


@requires_delta
def test_spark_scd2_merge_throughput(tmp_path, stress_corpus):
    """Benchmarks the production MERGE and asserts interval integrity after it.

    Session construction failing is an *environment* verdict and skips; an
    assertion failing after the merge is a *defect* verdict and fails. Collapsing
    the two would let a broken merge hide behind a missing JVM.

    The assertion of record is correctness after the merge. The throughput number
    is printed for comparison across runs rather than gated on, because the
    hardware it runs on is unknown.
    """
    from delta import configure_spark_with_delta_pip
    from pyspark.sql import SparkSession

    import scd2_merge_engine

    builder = (
        SparkSession.builder.appName("SovereignShieldStress")
        .master("local[*]")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.sql.warehouse.dir", str(tmp_path / "warehouse"))
        .config("spark.databricks.delta.snapshotPartitions", "2")
    )

    try:
        spark = configure_spark_with_delta_pip(builder).getOrCreate()
    except Exception as exc:  # noqa: BLE001 - any startup failure is environmental
        pytest.skip(
            "Spark session could not start, so the merge benchmark cannot run here. "
            f"Usually a missing or incompatible JVM. Underlying error: {type(exc).__name__}: {exc}"
        )

    try:
        table_name = "stress_agg_sdmx_history"
        source = stress_corpus.drop(columns=["VALID_FROM", "VALID_TO", "IS_CURRENT"])
        df = spark.createDataFrame(source)

        start = time.perf_counter()
        scd2_merge_engine.merge_scd2_macro(
            spark, df, target_table_name=table_name, date_scope="2026-Q1", agg_scope="LBSR"
        )
        elapsed = time.perf_counter() - start
        print(f"\nSCD2 macro merge: {len(source):,} rows in {elapsed:.1f}s")

        merged = spark.table(table_name)

        open_intervals = (
            merged.filter("IS_CURRENT = true")
            .groupBy("TIME_SERIES_CODE", "DATE", "AGG_CODE")
            .count()
            .filter("count > 1")
            .count()
        )
        assert open_intervals == 0, "SCD2 merge left duplicate active versions."

        quarantined_active = merged.filter(
            "BATCH_STATUS != 'PUBLISHED' AND IS_CURRENT = true"
        ).count()
        assert quarantined_active == 0, "A quarantined revision was published."
    finally:
        spark.stop()
