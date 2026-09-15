"""Build an isolated synthetic macro catalog without cloud credentials or a JVM."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generate_sovereign_submissions import aggregate_micro_to_macro, generate_micro_transactions, generate_sdmx_ml
from sdmx_rule_validator import SDMxRuleValidator
from submission_history import SubmissionContext, merge_local_submission


def build_demo(output):
    validator = SDMxRuleValidator()
    catalog = output / "catalog" / "agg_sdmx_history"
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".pytest_cache" / "demo")
    build_demo(parser.parse_args().output)