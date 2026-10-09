#!/usr/bin/env python3
"""Agent evals: incident-derived tasks scored by deterministic checks.

Each case in evals/cases/<id>.json comes from a defect this repository really
had; its "incident" field names the commit that fixed it. A case defines:

- prompt: the symptom, as an operator would report it to an agent;
- defect: exact find-and-replace edits that bring the defect back;
- violation: used instead of a defect, for edits a correct agent must never make;
- checks: pytest node ids that pass only once the defect is fixed;
- forbid: extra path patterns the agent must not change. tests/ and evals/ are
  always forbidden.

Modes:

  --self-test   Needs no agent and no API key. For every case, in a throwaway
                git worktree:
                - the checks pass at the ref;
                - each defect edit matches exactly once and turns the checks red;
                - each violation is caught by the forbidden-path scorer.
  --agent CMD   For every case, in a throwaway worktree where the defect is
                committed (so the tree starts clean), run CMD with the prompt
                appended as the final argument. Then score the result: the
                checks must pass and no forbidden path may change. Exit 1 when
                the pass rate is below --threshold.

The caller's checkout is never modified.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).resolve().parent / "cases"
ALWAYS_FORBIDDEN = ("tests/*", "evals/*")
REQUIRED = {"id", "incident", "summary", "prompt", "checks"}
IDENTITY = ("-c", "user.name=agent-evals", "-c", "user.email=agent-evals@localhost")


def validate(case: dict, stem: str) -> None:
    missing = REQUIRED - case.keys()
    if missing:
        raise ValueError(f"{stem}: missing {sorted(missing)}")
    if case["id"] != stem:
        raise ValueError(f"{stem}: id must match the file name")
    if bool(case.get("defect")) == bool(case.get("violation")):
        raise ValueError(f"{stem}: define exactly one of defect or violation")
    for edit in case.get("defect", []) + case.get("violation", []):
        if set(edit) != {"path", "find", "replace"} or not edit["find"] or edit["find"] == edit["replace"]:
            raise ValueError(f"{stem}: each edit needs path, find and a different replace")
    if not case["checks"] or not all(check.startswith("tests/") for check in case["checks"]):
        raise ValueError(f"{stem}: checks are pytest node ids under tests/")


def load_cases(directory: Path = CASES, selected: tuple = ()) -> list:
    cases = []
    for path in sorted(directory.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        validate(case, path.stem)
        if not selected or case["id"] in selected:
            cases.append(case)
    return cases


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


@contextlib.contextmanager
def worktree(ref: str):
    with tempfile.TemporaryDirectory(prefix="sovereignshield-eval-") as parent:
        tree = Path(parent) / "tree"
        git("worktree", "add", "--detach", str(tree), ref)
        try:
            yield tree
        finally:
            git("worktree", "remove", "--force", str(tree), check=False)
            git("worktree", "prune", check=False)


def apply(edits: list, tree: Path) -> None:
    for edit in edits:
        target = tree / edit["path"]
        with open(target, encoding="utf-8", newline="") as handle:
            text = handle.read()
        count = text.count(edit["find"])
        if count != 1:
            raise ValueError(f"{edit['path']}: find text occurs {count} times; update the case")
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace(edit["find"], edit["replace"]))


def run_checks(case: dict, tree: Path) -> tuple:
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", *case["checks"]]
    result = subprocess.run(command, cwd=tree, capture_output=True, text=True, timeout=900)
    return result.returncode == 0, (result.stdout + result.stderr)[-3000:]


def changed_paths(tree: Path, base: str) -> list:
    tracked = git("diff", "--name-only", base, cwd=tree).stdout.split()
    untracked = git("ls-files", "--others", "--exclude-standard", cwd=tree).stdout.split()
    return sorted(set(tracked) | set(untracked))


def forbidden(case: dict, paths: list) -> list:
    patterns = ALWAYS_FORBIDDEN + tuple(case.get("forbid", []))
    return [path for path in paths if any(fnmatch.fnmatch(path, pattern) for pattern in patterns)]


def self_test_case(case: dict, ref: str) -> str:
    """Returns an empty string when the case is meaningful, else the reason it is not."""
    with worktree(ref) as tree:
        passed, output = run_checks(case, tree)
        if not passed:
            return f"checks fail before any edit:\n{output}"
        base = git("rev-parse", "HEAD", cwd=tree).stdout.strip()
        try:
            apply(case.get("defect") or case["violation"], tree)
        except ValueError as error:
            return str(error)
        if case.get("defect"):
            passed, _ = run_checks(case, tree)
            return "checks still pass with the defect" if passed else ""
        return "" if forbidden(case, changed_paths(tree, base)) else "the violation is not caught by forbid"


def agent_case(case: dict, ref: str, agent: str, timeout: int) -> dict:
    started = time.monotonic()
    with worktree(ref) as tree:
        if case.get("defect"):
            apply(case["defect"], tree)
            git(*IDENTITY, "commit", "-q", "-am", f"eval {case['id']}: reintroduce the defect", cwd=tree)
        base = git("rev-parse", "HEAD", cwd=tree).stdout.strip()
        environment = {**os.environ, "SOVEREIGNSHIELD_FIX_MODE": "1"}
        try:
            run = subprocess.run([*shlex.split(agent), case["prompt"]], cwd=tree, env=environment,
                                 capture_output=True, text=True, timeout=timeout)
            agent_exit, tail = run.returncode, (run.stdout + run.stderr)[-2000:]
        except subprocess.TimeoutExpired:
            agent_exit, tail = "timeout", ""
        checks_passed, _ = run_checks(case, tree)
        touched = forbidden(case, changed_paths(tree, base))
    return {
        "id": case["id"], "passed": agent_exit == 0 and checks_passed and not touched, "checks_passed": checks_passed,
        "forbidden_changes": touched, "agent_exit": agent_exit,
        "seconds": round(time.monotonic() - started, 1), "agent_output_tail": tail,
    }


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true", help="prove every case reproduces its incident")
    mode.add_argument("--agent", help='agent command, for example "claude -p --permission-mode acceptEdits"')
    parser.add_argument("--ref", default="HEAD", help="commit to evaluate (default HEAD)")
    parser.add_argument("--case", action="append", default=[], help="run only this case id (repeatable)")
    parser.add_argument("--threshold", type=float, default=0.8, help="minimum agent pass rate")
    parser.add_argument("--timeout", type=int, default=1200, help="seconds allowed per agent run")
    parser.add_argument("--output", type=Path, help="write agent results as JSON")
    args = parser.parse_args(argv)
    cases = load_cases(selected=tuple(args.case))
    if not cases:
        parser.error("no cases selected")

    if args.self_test:
        failures = 0
        for case in cases:
            reason = self_test_case(case, args.ref)
            failures += bool(reason)
            print(f"{'FAIL' if reason else 'ok  '} {case['id']}" + (f": {reason}" if reason else ""))
        print(f"{len(cases) - failures}/{len(cases)} cases reproduce their incidents")
        return 1 if failures else 0

    results = [agent_case(case, args.ref, args.agent, args.timeout) for case in cases]
    rate = sum(result["passed"] for result in results) / len(results)
    for result in results:
        print(f"{'pass' if result['passed'] else 'FAIL'} {result['id']} ({result['seconds']} s)"
              + (f" agent exit: {result['agent_exit']}" if result["agent_exit"] != 0 else "")
              + (f" forbidden: {result['forbidden_changes']}" if result["forbidden_changes"] else ""))
    print(f"pass rate {rate:.0%} (threshold {args.threshold:.0%})")
    if args.output:
        args.output.write_text(json.dumps({"ref": args.ref, "pass_rate": rate, "threshold": args.threshold,
                                           "results": results}, indent=2) + "\n", encoding="utf-8")
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
