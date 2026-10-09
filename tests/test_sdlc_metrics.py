"""Process metrics come from git history alone (docs/AI_SDLC.md#metrics)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("sdlc_metrics", ROOT / "sh/sdlc_metrics.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def test_metrics_report_lead_times_and_trailer_coverage(tmp_path):
    def commit(path, text, when, *message):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        subprocess.run(["git", "-C", str(tmp_path), "add", path], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "-c", "commit.gpgsign=false", "commit", "-q", *sum((["-m", part] for part in message), [])],
                       check=True, env=env)

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    commit("README.md", "before the intent home\n", "2026-09-30T09:00:00+00:00", "Start")
    commit("intent/README.md", "# Intent Records\n", "2026-10-01T09:00:00+00:00", "Add the intent home")
    folder = "intent/2026-10-01-example"
    trailer = "Intent: 2026-10-01-example"
    commit(f"{folder}/intent.md", "# Intent: Example\n\n- **Status:** implemented\n",
           "2026-10-01T10:00:00+00:00", "Record the intent", trailer)
    commit(f"{folder}/spec.md", "# Spec\n", "2026-10-01T12:00:00+00:00", "Specify it", trailer)
    commit(f"{folder}/plan.md", "# Plan\n", "2026-10-01T13:00:00+00:00", "Plan it", trailer)
    commit("src/change.txt", "done\n", "2026-10-02T10:00:00+00:00", "Implement it", trailer)
    commit("notes.txt", "untraced\n", "2026-10-02T11:00:00+00:00", "Change without an intent")

    report = metrics.report(tmp_path)

    assert "| 2026-10-01-example | implemented | 2026-10-01 | 2.0 h | 3.0 h | 2026-10-02 | 24.0 h |" in report
    assert "4 of 6 non-merge commits (67%)" in report
