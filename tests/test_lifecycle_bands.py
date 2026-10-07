"""Lifecycle control bands and the timing record the lifecycle scripts write (docs/AI_SDLC.md)."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("check_lifecycle_bands", ROOT / "sh/check_lifecycle_bands.py")
bands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bands)

CONFIG = yaml.safe_load((ROOT / "ops/bands.yaml").read_text(encoding="utf-8"))
METRIC = next(metric for metric in CONFIG["metrics"] if metric["id"] == "up_total_minutes")
STEADY = [40.0, 42.0, 41.0, 43.0, 42.0, 41.0]


@pytest.mark.parametrize("points, tier, rule", [
    ([42.0], "baseline", None),
    (STEADY[:4] + [70.0], "baseline", None),
    (STEADY + [42.0], "ok", None),
    (STEADY + [43.0], "log", "beyond-1-sigma"),
    (STEADY + [44.0], "diagnose", "beyond-2-sigma"),
    (STEADY + [60.0], "propose", "beyond-3-sigma"),
    (STEADY + [30.0], "propose", "beyond-3-sigma"),
    ([41.0, 42.0] * 4 + [45.0, 45.0], "propose", "two-of-three-beyond-2-sigma"),
    ([38.0] * 3 + [42.0] * 8, "diagnose", "eight-on-one-side"),
])
def test_rules_fire_most_severe_first(points, tier, rule):
    result = bands.evaluate(points, METRIC, CONFIG["rules"])
    assert (result["tier"], result["rule"]) == (tier, rule)


def test_band_floor_keeps_a_perfectly_steady_baseline_from_flagging_noise():
    assert bands.evaluate([42.0] * 6 + [42.9], METRIC, CONFIG["rules"])["tier"] == "ok"


def test_committed_bands_and_history_are_well_formed():
    assert [rule["id"] for rule in CONFIG["rules"]] == list(bands.RULES)
    assert {rule["tier"] for rule in CONFIG["rules"]} <= set(CONFIG["tiers"])
    assert {metric["lifecycle"] for metric in CONFIG["metrics"]} == {"up", "down"}
    for line in (ROOT / CONFIG["history"]).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        assert record["lifecycle"] in ("up", "down") and record["outcome"] in ("complete", "incomplete")
        assert record["source"] in ("measured", "operator-reported") and record["total_minutes"] > 0
        assert re.match(r"\d{4}-\d{2}-\d{2}", record["started_at"])


@pytest.fixture
def estate(tmp_path):
    """A minimal checkout: bands, the intent index and an up history ending in a slow run."""
    (tmp_path / "ops").mkdir()
    shutil.copy(ROOT / "ops/bands.yaml", tmp_path / "ops/bands.yaml")
    (tmp_path / "intent").mkdir()
    shutil.copy(ROOT / "intent/README.md", tmp_path / "intent/README.md")
    runs = [("up", minutes, "complete") for minutes in STEADY] + [("up", 12.0, "incomplete"), ("up", 75.0, "complete")]
    (tmp_path / "ops/lifecycle_timings.jsonl").write_text("".join(
        json.dumps({"lifecycle": lifecycle, "started_at": f"2026-10-{day:02d}T09:00:00+00:00",
                    "total_minutes": minutes, "outcome": outcome, "source": "measured"}) + "\n"
        for day, (lifecycle, minutes, outcome) in enumerate(runs, start=1)), encoding="utf-8")
    return tmp_path


def test_propose_drafts_one_triageable_intent_and_indexes_it(estate, capsys):
    assert bands.main(["--lifecycle", "up", "--write-intent"], root=estate) == 0
    output = capsys.readouterr().out
    assert "75 min against 41.5" in output and "-> propose [beyond-3-sigma]" in output
    drafts = [path for path in (estate / "intent").iterdir() if path.name.endswith("-up-duration-change")]
    assert len(drafts) == 1
    draft = (drafts[0] / "intent.md").read_text(encoding="utf-8")
    template = (ROOT / "intent/_template/intent.md").read_text(encoding="utf-8")
    assert set(re.findall(r"^## .+$", template, re.MULTILINE)) <= set(re.findall(r"^## .+$", draft, re.MULTILINE))
    assert "- **Status:** draft" in draft and "- **Source:** control band" in draft
    assert "2026-10-08T09:00:00+00:00" in draft, "the incomplete run is history, not the latest point"
    index = (estate / "intent/README.md").read_text(encoding="utf-8")
    assert f"| [{drafts[0].name}]({drafts[0].name}/intent.md) | draft |" in index

    assert bands.main(["--lifecycle", "up", "--write-intent", "--strict"], root=estate) == 1
    assert (estate / "intent/README.md").read_text(encoding="utf-8") == index, "a rerun does not draft twice"


def test_malformed_bands_report_instead_of_raising(estate, capsys):
    (estate / "ops/bands.yaml").write_text(yaml.safe_dump({**CONFIG, "rules": [{"id": "gut-feel", "tier": "log"}]}),
                                           encoding="utf-8")
    assert bands.main([], root=estate) == 2
    assert "gut-feel" in capsys.readouterr().err


@pytest.mark.parametrize("script, scope", [
    ("sovereignshield_up.ps1", "$StartAtStage -eq 0 -and $StopAfterStage -eq 8 -and -not $SkipTests"),
    ("sovereignshield_down.ps1", '$Mode -eq "Workload" -and $ConfirmWorkloadDestruction -and -not $WhatIfPreference'),
])
def test_only_full_runs_are_recorded_after_the_timing_summary(script, scope):
    source = (ROOT / "sh" / script).read_text(encoding="utf-8")
    final = source[source.rindex("\nfinally {"):]
    assert final.index("Write-SovereignShieldTimingSummary") < final.index(scope) < final.index(
        "Add-SovereignShieldTimingRecord")
    record = final[final.index("Add-SovereignShieldTimingRecord"):]
    assert "-LifecycleLock $lifecycleLock" in record and "$lifecycleLock.Dispose()" in record
    assert "Dispose()" not in final[:final.index("Add-SovereignShieldTimingRecord")], "the lock outlives the record"


@pytest.mark.skipif(not shutil.which("pwsh"), reason="needs PowerShell 7")
def test_lifecycle_record_writer_waits_for_the_lifecycle_lock(estate):
    history = estate / "ops/lifecycle_timings.jsonl"
    before = history.read_text(encoding="utf-8")
    module = ROOT / "sh/lib/SovereignShield.Orchestration.psm1"
    script = f"""
Import-Module '{module}' -Force
$timings = [ordered]@{{ 'Preflight' = [TimeSpan]::FromMinutes(4) }}
$held = Enter-SovereignShieldLifecycleLock -RepoRoot '{estate}'
Add-SovereignShieldTimingRecord -RepoRoot '{estate}' -Lifecycle down -Timings $timings -StartedAt (Get-Date) -Completed $true
Write-Output "unlocked-lines=$((Get-Content '{history}').Count)"
Add-SovereignShieldTimingRecord -RepoRoot '{estate}' -Lifecycle down -Timings $timings -StartedAt (Get-Date) -Completed $true -LifecycleLock $held
$held.Dispose()
"""
    result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"unlocked-lines={len(before.splitlines())}" in result.stdout
    assert "Another lifecycle operation holds" in result.stdout + result.stderr
    added = history.read_text(encoding="utf-8")[len(before):].splitlines()
    assert len(added) == 1 and json.loads(added[0])["lifecycle"] == "down"


@pytest.mark.skipif(not shutil.which("pwsh"), reason="needs PowerShell 7")
def test_lifecycle_record_writer_appends_one_line_and_never_throws(estate):
    (estate / "sh").mkdir()
    shutil.copy(ROOT / "sh/check_lifecycle_bands.py", estate / "sh")
    if os.name != "nt":
        python = estate / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        python.chmod(0o755)
    history = estate / "ops/lifecycle_timings.jsonl"
    before = history.read_text(encoding="utf-8")
    module = ROOT / "sh/lib/SovereignShield.Orchestration.psm1"
    script = f"""
Import-Module '{module}' -Force
$timings = [ordered]@{{ 'Preflight' = [TimeSpan]::FromMinutes(4); 'Terraform destroy (incomplete)' = [TimeSpan]::FromSeconds(30) }}
Add-SovereignShieldTimingRecord -RepoRoot '{estate}' -Lifecycle down -Timings $timings -StartedAt (Get-Date).AddMinutes(-5) -Completed $false
Add-SovereignShieldTimingRecord -RepoRoot '{estate / "missing"}' -Lifecycle down -Timings $timings -StartedAt (Get-Date) -Completed $true
"""
    result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    after = history.read_text(encoding="utf-8")
    assert after.startswith(before)
    added = [json.loads(line) for line in after[len(before):].splitlines()]
    assert len(added) == 1
    assert {key: added[0][key] for key in ("lifecycle", "outcome", "source")} == {
        "lifecycle": "down", "outcome": "incomplete", "source": "measured"}
    assert 4.9 <= added[0]["total_minutes"] <= 7
    assert added[0]["steps"] == {"Preflight": 4, "Terraform destroy (incomplete)": 0.5}
    assert "was not recorded" in result.stdout + result.stderr
    if os.name != "nt":
        assert "down_total_minutes: building the baseline" in result.stdout
