#!/usr/bin/env python3
"""Process metrics for the AI-native SDLC (docs/AI_SDLC.md#metrics).

Reads only git history, so any clone reproduces the numbers. For each intent
folder it reports when intent.md, spec.md and plan.md were first committed, the
last commit carrying its `Intent:` trailer, and the lead time from committed
intent to that commit. It also reports the share of non-merge commits since the
intent home was created that carry an `Intent:` trailer.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = re.compile(r"^- \*\*Status:\*\* (\S+)$", re.MULTILINE)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def first_commit_time(repo, path):
    times = git(repo, "log", "--diff-filter=A", "--format=%cI", "--", path).split()
    return datetime.fromisoformat(times[-1]) if times else None


def trailer_commits(repo, since=None):
    """Yields (sha, committed_at, [intent ids]) for non-merge commits, newest first."""
    # <since>^@ is every parent of <since>, so the range includes <since> itself, even as a root commit.
    revision = ["HEAD", "--not", f"{since}^@"] if since else ["HEAD"]
    log = git(repo, "log", "--no-merges", "--format=%H%x09%cI%x09%(trailers:key=Intent,valueonly,separator=%x2C)",
              *revision)
    for line in log.splitlines():
        sha, committed, intents = (line.split("\t") + [""])[:3]
        yield sha, datetime.fromisoformat(committed), [value.strip() for value in intents.split(",") if value.strip()]


def duration(start, end):
    if not start or not end:
        return "-"
    hours = (end - start).total_seconds() / 3600
    return f"{hours:.1f} h" if hours < 48 else f"{hours / 24:.1f} d"


def report(repo):
    intents = sorted(path for path in (repo / "intent").iterdir() if path.is_dir() and path.name != "_template")
    adoption = git(repo, "log", "--diff-filter=A", "--format=%H", "--", "intent/README.md").split()
    commits = list(trailer_commits(repo, adoption[-1] if adoption else None))
    lines = [
        "| Intent | Status | Intent committed | Spec after | Plan after | Last trailer commit | Intent to last commit |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for folder in intents:
        relative = folder.relative_to(repo).as_posix()
        match = STATUS.search((folder / "intent.md").read_text(encoding="utf-8"))
        status = match.group(1) if match else "unknown"
        created = {name: first_commit_time(repo, f"{relative}/{name}") for name in ("intent.md", "spec.md", "plan.md")}
        tagged = [committed for _, committed, ids in commits if folder.name in ids]
        last = max(tagged) if tagged else None
        # A retrospective intent is written after its commits, so it has no lead time.
        lead = "retrospective" if status == "retrospective" else duration(created["intent.md"], last)
        lines.append(" | ".join([
            f"| {folder.name}", status,
            created["intent.md"].date().isoformat() if created["intent.md"] else "uncommitted",
            duration(created["intent.md"], created["spec.md"]), duration(created["intent.md"], created["plan.md"]),
            last.date().isoformat() if last else "-", f"{lead} |",
        ]))
    with_trailer = sum(1 for _, _, ids in commits if ids)
    share = f"{100 * with_trailer / len(commits):.0f}%" if commits else "-"
    lines.append("")
    lines.append(f"Intent trailer coverage since the intent home was created: {with_trailer} of {len(commits)} "
                 f"non-merge commits ({share}).")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", type=Path, default=ROOT, help="repository root (default: this checkout)")
    args = parser.parse_args(argv)
    print(report(args.repo.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
