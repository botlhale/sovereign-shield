"""Agent eval cases stay well-formed and, with --evals, still reproduce their incidents."""

import contextlib
import importlib.util
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_evals", ROOT / "evals/run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)


def test_cases_are_well_formed_and_target_the_current_code():
    cases = run_evals.load_cases()
    assert len(cases) >= 8
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        if not re.fullmatch(r"[0-9a-f]{7,40}", case["incident"]):
            assert (ROOT / "intent" / case["incident"] / "intent.md").is_file(), case["id"]
        for check in case["checks"]:
            path, _, name = check.partition("::")
            assert not name or f"def {name}(" in (ROOT / path).read_text(encoding="utf-8"), check
        for edit in case.get("defect", []) + case.get("violation", []):
            text = (ROOT / edit["path"]).read_text(encoding="utf-8")
            assert text.count(edit["find"]) == 1, f"{case['id']}: {edit['path']} drifted; update the case"


def test_validation_rejects_ambiguous_cases():
    base = {"id": "x", "incident": "abc1234", "summary": "s", "prompt": "p", "checks": ["tests/test_x.py"]}
    with pytest.raises(ValueError, match="exactly one"):
        run_evals.validate(base, "x")
    with pytest.raises(ValueError, match="different replace"):
        run_evals.validate({**base, "defect": [{"path": "a", "find": "b", "replace": "b"}]}, "x")
    with pytest.raises(ValueError, match="file name"):
        run_evals.validate({**base, "defect": [{"path": "a", "find": "b", "replace": "c"}]}, "y")
    with pytest.raises(ValueError, match="node ids"):
        run_evals.validate({**base, "checks": ["test_x.py"], "defect": [{"path": "a", "find": "b", "replace": "c"}]}, "x")


def test_tests_and_evals_are_always_forbidden_to_the_agent():
    case = {"forbid": ["src/unity_catalog_grants.sql"]}
    changed = ["README.md", "tests/unit/test_a.py", "evals/cases/x.json", "src/unity_catalog_grants.sql"]
    assert run_evals.forbidden(case, changed) == changed[1:]


@pytest.mark.parametrize("exit_code, passed", [(0, True), (3, False)])
def test_an_agent_that_fails_or_crashes_does_not_pass(monkeypatch, tmp_path, exit_code, passed):
    monkeypatch.setattr(run_evals, "worktree", lambda ref: contextlib.nullcontext(tmp_path))
    monkeypatch.setattr(run_evals, "git", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "abc\n", ""))
    monkeypatch.setattr(run_evals, "run_checks", lambda case, tree: (True, ""))
    monkeypatch.setattr(run_evals, "changed_paths", lambda tree, base: [])
    case = {"id": "x", "prompt": "p", "violation": [{"path": "a", "find": "b", "replace": "c"}]}
    agent = shlex.join([sys.executable, "-c", f"import sys; sys.exit({exit_code})"])
    result = run_evals.agent_case(case, "HEAD", agent, timeout=60)
    assert (result["agent_exit"], result["passed"]) == (exit_code, passed)


@pytest.mark.evals
def test_every_case_reproduces_its_incident_at_head():
    assert run_evals.main(["--self-test"]) == 0
