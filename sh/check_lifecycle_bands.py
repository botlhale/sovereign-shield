#!/usr/bin/env python3
"""Deterministic control bands for lifecycle durations (Maintain stage, docs/AI_SDLC.md).

Reads ops/bands.yaml and the run history in ops/lifecycle_timings.jsonl. For each
metric it compares the latest complete run with the mean and standard deviation
of the complete runs before it, and reports the tier of the first rule that
fires:

  propose        a draft intent is due; --write-intent writes it under intent/
  diagnose       the service owner compares the flagged runs' step timings
  log            noted in the summary; no action
  ok / baseline  inside the bands, or not enough history yet

The baseline is the complete runs before the latest, so a slow run cannot hide
inside its own band. Incomplete runs stay in the history but are excluded from
the bands. The lifecycle scripts run this after every full run and only warn if
it fails. Exit status: 2 for malformed input, 1 with --strict when a metric
reaches propose, otherwise 0.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _beyond(multiple):
    return lambda points, mean, sigma: abs(points[-1] - mean) > multiple * sigma


def _two_of_three(points, mean, sigma):
    recent = points[-3:]
    for side in (1, -1):
        hits = [side * (point - mean) > 2 * sigma for point in recent]
        if hits[-1] and sum(hits) >= 2:
            return True
    return False


def _eight_on_one_side(points, mean, sigma):
    recent = points[-8:]
    return len(recent) == 8 and (all(point > mean for point in recent) or all(point < mean for point in recent))


RULES = {
    "beyond-3-sigma": _beyond(3),
    "two-of-three-beyond-2-sigma": _two_of_three,
    "eight-on-one-side": _eight_on_one_side,
    "beyond-2-sigma": _beyond(2),
    "beyond-1-sigma": _beyond(1),
}


def evaluate(points, metric, rules):
    """points: complete-run values in chronological order, latest last."""
    previous = points[:-1][-metric["window"]:]
    result = {"metric": metric["id"], "latest": points[-1] if points else None, "n": len(previous),
              "min_runs": metric["min_runs"]}
    if not points or len(previous) < metric["min_runs"]:
        return {**result, "tier": "baseline", "rule": None}
    mean = statistics.fmean(previous)
    sigma = max(statistics.stdev(previous) if len(previous) > 1 else 0.0, metric["min_sigma"])
    result.update(mean=round(mean, 1), sigma=round(sigma, 2))
    for rule in rules:
        if RULES[rule["id"]](points, mean, sigma):
            return {**result, "tier": rule["tier"], "rule": rule["id"]}
    return {**result, "tier": "ok", "rule": None}


def load(root):
    config = yaml.safe_load((root / "ops/bands.yaml").read_text(encoding="utf-8"))
    unknown = [rule["id"] for rule in config["rules"] if rule["id"] not in RULES]
    if unknown:
        raise ValueError(f"unknown rule ids in ops/bands.yaml: {unknown}")
    history_path = root / config["history"]
    lines = history_path.read_text(encoding="utf-8").splitlines() if history_path.exists() else []
    history = [json.loads(line) for line in lines if line.strip()]
    return config, history


def check(root, lifecycle=None):
    config, history = load(root)
    results = []
    for metric in config["metrics"]:
        if lifecycle and metric["lifecycle"] != lifecycle:
            continue
        runs = [run for run in history if run.get("lifecycle") == metric["lifecycle"] and run.get("outcome") == "complete"]
        result = evaluate([float(run[metric["field"]]) for run in runs], metric, config["rules"])
        result.update(lifecycle=metric["lifecycle"], started_at=runs[-1]["started_at"] if runs else None)
        results.append(result)
    return results


def describe(result):
    if result["tier"] == "baseline":
        return (f"{result['metric']}: building the baseline "
                f"({result['n']} of {result['min_runs']} earlier complete runs)")
    return (f"{result['metric']}: {result['latest']:g} min against {result['mean']:g} ± {result['sigma']:g} "
            f"(n={result['n']}) -> {result['tier']}" + (f" [{result['rule']}]" if result["rule"] else ""))


def write_intent(root, result, today=None):
    """Drafts an intent for a propose result, keyed by the flagged run's start date.

    Returns its folder, or None if that run already has one.
    """
    today = today or date.today().isoformat()
    run_date = date.fromisoformat(str(result["started_at"])[:10]).isoformat()
    folder_name = f"{run_date}-{result['lifecycle']}-duration-change"
    folder = root / "intent" / folder_name
    if folder.exists():
        return None
    folder.mkdir(parents=True)
    script = f"sh/sovereignshield_{result['lifecycle']}.ps1"
    (folder / "intent.md").write_text(f"""# Intent: Explain the change in {result['lifecycle']} lifecycle duration

- **Status:** draft
- **Originator:** Control band `{result['metric']}` (`sh/check_lifecycle_bands.py`)
- **Product owner:** @botlhale
- **Date:** {today}
- **Source:** control band

## Problem

The {result['lifecycle']} run started {result['started_at']} took {result['latest']:g} minutes against a
baseline of {result['mean']:g} ± {result['sigma']:g} minutes over the previous {result['n']} complete runs.
Rule `{result['rule']}` fired. The run's step timings are in `ops/lifecycle_timings.jsonl`.

## Proposed outcome

The cause is understood, and the {result['lifecycle']} duration either returns inside its
control band or the band is re-baselined with a recorded reason.

## Affected users and systems

Operators of `{script}`, and the Azure and Databricks resources it manages.

## Constraints

- Lifecycle timings remain synthetic evaluation evidence (`docs/RELEASE_EVIDENCE.md`).
- The bands are not widened to silence the signal without a recorded reason.

## Open questions

- Was the run comparable: same scope, region and prerequisites?
- Which step moved? Compare its `steps` with those of the baseline runs.
""", encoding="utf-8")
    index = root / "intent/README.md"
    lines = index.read_text(encoding="utf-8").splitlines()
    start = lines.index("## Index")
    last_row = max(number for number in range(start, len(lines)) if lines[number].startswith("|"))
    lines.insert(last_row + 1, f"| [{folder_name}]({folder_name}/intent.md) | draft | "
                               f"Explain the change in {result['lifecycle']} lifecycle duration (control band) |")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lifecycle", choices=("up", "down"), help="check only this lifecycle")
    parser.add_argument("--write-intent", action="store_true", help="draft an intent for every propose result")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a metric reaches propose")
    args = parser.parse_args(argv)
    try:
        results = check(root, args.lifecycle)
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"Control bands could not be checked: {error}", file=sys.stderr)
        return 2
    for result in results:
        print(f"Control band {describe(result)}")
        if result["tier"] == "propose" and args.write_intent:
            try:
                folder = write_intent(root, result)
            except ValueError as error:
                print(f"  Draft intent not written: {error}", file=sys.stderr)
                continue
            if folder:
                print(f"  Draft intent written to {folder.relative_to(root).as_posix()}/intent.md for triage.")
    return 1 if args.strict and any(result["tier"] == "propose" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
