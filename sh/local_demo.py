"""Build an isolated synthetic macro catalog without cloud credentials or a JVM."""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from deltalake import DeltaTable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from decimal_measures import decimal_text
from generate_sovereign_submissions import aggregate_micro_to_macro, generate_micro_transactions, generate_sdmx_ml
from sdmx_rule_validator import SDMxRuleValidator
from submission_history import HISTORY_COLUMNS, SubmissionContext, merge_local_submission

DATABRICKS_VARIABLES = ("DATABRICKS_HOST", "DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_WAREHOUSE_ID")
PERSONAS = {
    "public": {"sg-sovereignshield-public"},
    "researcher": {"sg-sovereignshield-researchers"},
    "submitter-ca": {"sg-sovereignshield-submitter-ca"},
    "submitter-us": {"sg-sovereignshield-submitter-us"},
    "admin": {"sg-sovereignshield-admin"},
}


def build_demo(output, migrate_legacy=False):
    validator = SDMxRuleValidator()
    catalog = output / "catalog" / "agg_sdmx_history"
    if (catalog / "_delta_log").exists():
        missing = sorted(set(HISTORY_COLUMNS) - {field.name for field in DeltaTable(str(catalog)).schema().fields})
        if missing and not migrate_legacy:
            raise SystemExit(
                f"{catalog} predates the current history contract (missing {', '.join(missing)}). Rerun with "
                "--migrate-legacy to preserve it and replay the archived arrivals, or choose a new --output."
            )
        if missing:
            # Outside catalog/, so the policy mirror never reads the preserved legacy rows.
            archive = output / "legacy" / f"agg_sdmx_history-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
            archive.parent.mkdir(parents=True, exist_ok=True)
            catalog.rename(archive)
            print(f"Legacy history preserved at {archive.resolve()}; replaying archived arrivals.")
    for cycle in ("baseline", "revision"):
        directory = output / "arrivals" / cycle
        directory.mkdir(parents=True, exist_ok=True)
        for country, micro in generate_micro_transactions(cycle).items():
            paths = list(directory.glob(f"{country}_submission*.xml"))
            if not paths:
                paths = [Path(generate_sdmx_ml(
                    aggregate_micro_to_macro(micro), country,
                    submission_type="First Submission" if cycle == "baseline" else "Revision",
                    output_dir=str(directory),
                ))]
            for path in paths:
                submitted = validator.load_submission(str(path))
                context = SubmissionContext(
                    submitted.attrs["SUBMISSION_ID"], submitted.attrs["SOURCE_SHA256"],
                    submitted.attrs["SUBMITTED_AT"].to_pydatetime(), datetime.now(timezone.utc),
                )
                merge_local_submission(catalog, validator.validate(submitted), context)
    print(f"Local synthetic catalog: {catalog.parent.resolve()}")


def show_persona(output, persona):
    """Print the current published view through the local policy mirror."""
    from uc_query import LocalDeltaBackend, Principal, SeriesFilter

    principal = Principal(persona, frozenset(PERSONAS[persona]), persona != "public")
    rows = LocalDeltaBackend(str(output / "catalog")).search(SeriesFilter.build(limit=500), principal)
    withheld = int(rows["OBS_VALUE"].isna().sum())
    print(f"\n{principal.access_label}: {len(rows)} observation(s), {withheld} withheld")
    for row in rows.to_dict("records"):
        value = decimal_text(row["OBS_VALUE"]) or "restricted"
        print(f"  {row['TIME_SERIES_CODE']:<34} {row['DATE']}  {value:>12}  {row['OBS_CONF']}")


def serve(persona, port):
    """Serve the portal on localhost with a labelled persona fixture over the local mirror."""
    if any(os.getenv(name) for name in DATABRICKS_VARIABLES):
        raise SystemExit("Unset Databricks connection variables: persona fixtures serve the local mirror only.")
    import uvicorn

    import api_gateway
    from uc_query import Principal

    fixture = Principal(f"Local {persona} fixture", frozenset(PERSONAS[persona]), persona != "public")
    api_gateway.app.dependency_overrides[api_gateway.current_principal] = lambda: fixture
    print(f"Serving the synthetic {persona} fixture at http://127.0.0.1:{port}/")
    uvicorn.run(api_gateway.app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".pytest_cache" / "demo")
    parser.add_argument("--persona", choices=sorted(PERSONAS), action="append", default=[])
    parser.add_argument("--serve", choices=sorted(PERSONAS), help="serve the local portal as this persona fixture")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--migrate-legacy", action="store_true",
                        help="preserve an incompatible local history under legacy/ and replay the archived arrivals")
    args = parser.parse_args()
    os.environ["SOVEREIGNSHIELD_LOCAL_DELTA"] = str(args.output / "catalog")
    build_demo(args.output, migrate_legacy=args.migrate_legacy)
    for selected in args.persona:
        show_persona(args.output, selected)
    if args.serve:
        serve(args.serve, args.port)