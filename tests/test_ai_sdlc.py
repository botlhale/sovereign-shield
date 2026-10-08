"""The AI-native SDLC artifacts stay complete and the agent gates keep working.

See docs/AI_SDLC.md. These checks are structural on purpose. They prove that:

- every change has the intent, spec and plan its status requires;
- the agent instructions, skills and subagents load;
- the shared PreToolUse gate makes the right decision for each gated action, in
  both the Claude Code and the VS Code payload shapes;
- the AI workflows stay pinned, least-privileged and inert without their secret.
"""

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
INTENTS = ROOT / "intent"
GATE = ROOT / ".claude/hooks/pretool_gate.py"
STATUS = re.compile(r"^- \*\*Status:\*\* (\S+)$", re.MULTILINE)
FOLDER = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
STATUSES = ("draft", "accepted", "specified", "planned", "implemented", "verified", "rejected", "retrospective")
SECTIONS = {
    "intent.md": ("Problem", "Proposed outcome", "Affected users and systems", "Constraints", "Open questions"),
    "spec.md": ("Requirements", "Design", "Flagged concerns", "Acceptance criteria", "Out of scope"),
    "plan.md": ("Files that change", "Order of work", "Risks", "Proof", "Rollback", "Evidence"),
}
REQUIRED_BY_STATUS = {
    "spec.md": ("specified", "planned", "implemented", "verified"),
    "plan.md": ("planned", "implemented", "verified"),
}

spec = importlib.util.spec_from_file_location("pretool_gate", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _intent_folders():
    return sorted(path for path in INTENTS.iterdir() if path.is_dir() and path.name != "_template")


def _headings(path):
    return set(re.findall(r"^## (.+?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE))


def _status(folder):
    return STATUS.search((folder / "intent.md").read_text(encoding="utf-8")).group(1)


def test_templates_define_every_section():
    for name, sections in SECTIONS.items():
        assert set(sections) <= _headings(INTENTS / "_template" / name), name


@pytest.mark.parametrize("folder", _intent_folders(), ids=lambda path: path.name)
def test_intent_records_carry_the_artifacts_their_status_requires(folder):
    assert FOLDER.match(folder.name)
    intent = (folder / "intent.md").read_text(encoding="utf-8")
    assert STATUS.search(intent), "intent.md states its status"
    status = _status(folder)
    assert status in STATUSES
    assert set(SECTIONS["intent.md"]) <= _headings(folder / "intent.md")
    for artifact, statuses in REQUIRED_BY_STATUS.items():
        if status in statuses:
            assert set(SECTIONS[artifact]) <= _headings(folder / artifact), artifact
    if status == "verified":
        placeholder = (INTENTS / "_template/plan.md").read_text(encoding="utf-8").split("## Evidence", 1)[1].strip()
        evidence = (folder / "plan.md").read_text(encoding="utf-8").split("## Evidence", 1)[1]
        assert placeholder and placeholder not in evidence
        assert "Completed when the status becomes verified" not in evidence
    if status == "retrospective":
        assert "Retrospective record" in _headings(folder / "intent.md")
        assert re.search(r"`[0-9a-f]{7,40}`", intent), "a retrospective cites its commits"


def test_index_lists_every_intent_with_its_status():
    index = (INTENTS / "README.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| \[([^\]]+)\]\(\1/intent\.md\) \| (\w+) \|", index, re.MULTILINE))
    assert rows == {folder.name: _status(folder) for folder in _intent_folders()}


def test_claude_md_imports_the_shared_instructions_and_stays_short():
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in claude.splitlines()
    assert len(claude.splitlines()) <= 40
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for heading in ("How Work Flows", "Commands", "Verification Block", "Architecture", "Skills", "Rules",
                    "Things Agents Get Wrong"):
        assert f"\n## {heading}\n" in agents, heading


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path.relative_to(ROOT)} has no frontmatter"
    return yaml.safe_load(match.group(1)), text[match.end():]


def test_skills_load_in_claude_code_and_vs_code_and_are_listed_for_every_agent():
    skills = sorted((ROOT / ".claude/skills").glob("*/SKILL.md"))
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(skills) >= 8
    for path in skills:
        meta, body = _frontmatter(path)
        assert meta["name"] == path.parent.name
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", meta["name"]) and len(meta["name"]) <= 64
        assert 40 <= len(meta["description"]) <= 1024 and "Use " in meta["description"]
        assert f"`{meta['name']}`" in agents, f"AGENTS.md lists {meta['name']}"
        assert body.strip()


def test_subagents_review_and_verify_without_editing():
    for name in ("verifier", "policy-reviewer"):
        meta, body = _frontmatter(ROOT / f".claude/agents/{name}.md")
        assert meta["name"] == name and meta["description"]
        assert not {"Edit", "Write", "MultiEdit", "NotebookEdit"} & {tool.strip() for tool in meta["tools"].split(",")}
        assert "never edit" in body


@pytest.fixture
def isolated_gate(tmp_path):
    """A copy of the gate whose repository root is tmp_path, so local state cannot leak in."""
    hooks = tmp_path / ".claude/hooks"
    hooks.mkdir(parents=True)
    shutil.copy(GATE, hooks / GATE.name)

    def run(payload, **environment):
        env = {key: value for key, value in os.environ.items() if key != "SOVEREIGNSHIELD_FIX_MODE"}
        env.update(environment)
        text = json.dumps(payload).replace("{root}", tmp_path.as_posix())
        result = subprocess.run([sys.executable, str(hooks / GATE.name)], input=text, capture_output=True,
                                text=True, env=env, timeout=30)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] if result.stdout else None

    run.root = tmp_path
    return run


@pytest.mark.parametrize("tool, command, expected", [
    ("Bash", "pwsh ./sh/sovereignshield_up.ps1 -AccountId x -TenantDomain y", "ask"),
    ("run_in_terminal", "pwsh ./sh/sovereignshield_down.ps1 -Mode Workload -ConfirmWorkloadDestruction", "ask"),
    ("Bash", "bash scripts/sovereign_down_custom.sh", "ask"),
    ("Bash", "terraform -chdir=terraform destroy -auto-approve", "ask"),
    ("Bash", "cd terraform && terraform apply tfplan", "ask"),
    ("run_in_terminal", "az group delete --name rg-sovereignshield --yes", "ask"),
    ("Bash", "databricks -p dev bundle deploy -t dev", "ask"),
    ("Bash", "python scripts/apply_policies.py --target dev", "ask"),
    ("run_in_terminal", "git -c user.name=a push origin main", "ask"),
    ("Bash", "gh pr merge 7 --squash", "ask"),
    ("run_in_terminal", "pwsh .\\sh\\SovereignShield_Up.ps1 -AccountId x", "ask"),
    ("run_in_terminal", "Terraform -chdir=terraform Destroy", "ask"),
    ("Bash", "python -m pytest tests/ -q", None),
    ("run_in_terminal", "git commit -m 'push the docs and terraform notes'", None),
    ("Bash", "az monitor activity-log list --query \"[?contains(operationName.value,'delete')]\"", None),
    ("Bash", "terraform -chdir=terraform validate", None),
    ("send_to_terminal", "databricks warehouses list", None),
])
def test_gate_asks_before_cloud_and_publishing_commands(isolated_gate, tool, command, expected):
    assert isolated_gate({"tool_name": tool, "tool_input": {"command": command}}) == expected


@pytest.mark.parametrize("payload, environment, expected", [
    ({"tool_name": "Edit", "tool_input": {"file_path": "{root}/src/unity_catalog_grants.sql"}}, {}, "ask"),
    ({"tool_name": "replace_string_in_file", "tool_input": {"filePath": "{root}/src/apply_security.py"}}, {}, "ask"),
    ({"tool_name": "apply_patch", "tool_input": {
        "input": "*** Begin Patch\n*** Update File: {root}/scripts/apply_policies.py\n*** End Patch"}}, {}, "ask"),
    ({"tool_name": "Write", "tool_input": {"file_path": "{root}/tests/test_new.py"}}, {}, None),
    ({"tool_name": "Write", "tool_input": {"file_path": "{root}/tests/test_new.py"}},
     {"SOVEREIGNSHIELD_FIX_MODE": "1"}, "deny"),
    ({"tool_name": "multi_replace_string_in_file", "tool_input": {"replacements": [
        {"filePath": "{root}/README.md"}, {"filePath": "{root}/evals/cases/case.json"}]}},
     {"SOVEREIGNSHIELD_FIX_MODE": "1"}, "deny"),
    ({"tool_name": "Read", "tool_input": {"file_path": "{root}/terraform/terraform.tfstate"}}, {}, "deny"),
    ({"tool_name": "read_file", "tool_input": {"filePath": "{root}/.env"}}, {}, "deny"),
    ({"tool_name": "Read", "tool_input": {"file_path": "~/.ssh/id_rsa"}}, {}, "deny"),
    ({"tool_name": "read_file", "tool_input": {"filePath": "{root}/.ssh/id_ed25519"}}, {}, "deny"),
    ({"tool_name": "read_file", "tool_input": {"filePath": "{root}/README.md"}}, {}, None),
    ({"tool_name": "grep_search", "tool_input": {"query": "password"}}, {}, None),
    ({"tool_name": "grep_search", "tool_input": {"query": "password", "includePattern": "**/.env"}}, {}, "deny"),
    ({"tool_name": "grep_search", "tool_input": {"query": "key", "includePattern": "{README.md,.ssh/*}"}}, {}, "deny"),
    ({"tool_name": "Grep", "tool_input": {"pattern": "secret", "path": "{root}/terraform/terraform.tfstate"}}, {},
     "deny"),
    ({"tool_name": "Grep", "tool_input": {"pattern": "token", "glob": "*.tfstate"}}, {}, "deny"),
    ({"tool_name": "Grep", "tool_input": {"pattern": "token", "path": "~/.SSH"}}, {}, "deny"),
    ({"tool_name": "Grep", "tool_input": {"pattern": "def ", "path": "{root}/src", "glob": "*.py"}}, {}, None),
])
def test_gate_protects_policy_files_credentials_and_tests_in_fix_mode(isolated_gate, payload, environment, expected):
    assert isolated_gate(payload, **environment) == expected


WRITE_TEST = "python -c \"open('tests/test_new.py', 'w').write('def test_x(): pass')\""


@pytest.mark.parametrize("tool, command, environment, expected", [
    ("Bash", "cat .env", {}, "deny"),
    ("run_in_terminal", "cat ~/.ssh/id_ed25519", {}, "deny"),
    ("Bash", "terraform -chdir=terraform show terraform.tfstate", {}, "deny"),
    ("Bash", WRITE_TEST, {}, None),
    ("Bash", WRITE_TEST, {"SOVEREIGNSHIELD_FIX_MODE": "1"}, "deny"),
    ("run_in_terminal", WRITE_TEST, {"SOVEREIGNSHIELD_FIX_MODE": "1"}, "deny"),
    ("run_in_terminal", "cd tests && touch test_new.py", {"SOVEREIGNSHIELD_FIX_MODE": "1"}, "deny"),
    ("Bash", "python -m pytest tests/ -q > tests/out.txt", {"SOVEREIGNSHIELD_FIX_MODE": "1"}, "deny"),
    ("Bash", "python -m pytest tests/ -q & rm tests/test_x.py", {"SOVEREIGNSHIELD_FIX_MODE": "1"}, "deny"),
    ("Bash", "python -m pytest tests/ -q 2>&1 | tail -n 20", {"SOVEREIGNSHIELD_FIX_MODE": "1"}, None),
    ("run_in_terminal", "python evals/run_evals.py --self-test", {"SOVEREIGNSHIELD_FIX_MODE": "1"}, None),
    ("Bash", "git diff tests/", {"SOVEREIGNSHIELD_FIX_MODE": "1"}, None),
])
def test_gate_holds_credential_and_fix_mode_rules_in_terminal_commands(isolated_gate, tool, command, environment,
                                                                       expected):
    assert isolated_gate({"tool_name": tool, "tool_input": {"command": command}}, **environment) == expected


def test_fix_mode_marker_locks_tests_and_guards_itself(isolated_gate):
    edit_test = {"tool_name": "create_file", "tool_input": {"filePath": "{root}/tests/test_new.py"}}
    assert isolated_gate(edit_test) is None
    (isolated_gate.root / gate.FIX_MARKER).touch()
    assert isolated_gate(edit_test) == "deny"
    assert isolated_gate({"tool_name": "Bash", "tool_input": {"command": f"rm {gate.FIX_MARKER}"}}) == "ask"


def test_gate_warns_instead_of_blocking_on_malformed_input():
    result = subprocess.run([sys.executable, str(GATE)], input="not json", capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and not result.stdout and "pretool_gate" in result.stderr


def test_both_agent_harnesses_run_the_same_gate():
    claude = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    assert any(
        "pretool_gate.py" in hook["command"] and {"Bash", "Edit", "Write", "Read", "Grep"} <= set(entry["matcher"].split("|"))
        for entry in claude["hooks"]["PreToolUse"] for hook in entry["hooks"]
    )
    assert {"Read(./.env)", "Read(./**/*.tfstate)"} <= set(claude["permissions"]["deny"])
    vscode = json.loads((ROOT / ".github/hooks/sovereignshield.json").read_text(encoding="utf-8"))
    assert vscode["hooks"]["PreToolUse"] and all(
        "pretool_gate.py" in hook["command"] for hook in vscode["hooks"]["PreToolUse"])
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert gate.FIX_MARKER in ignored and ".claude/settings.local.json" in ignored


def test_policy_owner_files_agree_across_gate_review_owners_and_instructions():
    review = (ROOT / "REVIEW.md").read_text(encoding="utf-8")
    owners = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for path in gate.POLICY_FILES:
        assert f"`{path}`" in review and f"`{path}`" in agents
        assert re.search(rf"^/{re.escape(path)}\s+@\w", owners, re.MULTILINE), path


def test_review_criteria_and_template_close_the_loop():
    review = (ROOT / "REVIEW.md").read_text(encoding="utf-8")
    for heading in ("### 1. Bugs", "### 2. Security and Data", "### 3. Compliance with Intent, Spec and Plan",
                    "### 4. Evidence and Claims", "## Severity", "## Do Not Report", "## Output"):
        assert heading in review
    assert "at most five" in review
    owners = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    assert re.search(r"^\*\s+@\w", owners, re.MULTILINE)
    for path in ("/AGENTS.md", "/CLAUDE.md", "/REVIEW.md", "/.claude/", "/.github/workflows/"):
        assert re.search(rf"^{re.escape(path)}\s+@\w", owners, re.MULTILINE), path
    template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert "## Intent" in template and "`Intent:`" in template
    assert "CONTRIBUTING.md#ai-assisted-software-development-life-cycle" in template


def _workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_every_workflow_action_is_pinned_to_a_commit():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        for target in re.findall(r"^\s*(?:-\s+)?uses:\s*(.+?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE):
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d[\w.]*", target), f"{path.name}: {target}"


@pytest.mark.parametrize("name", sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml")
                                         if "ANTHROPIC_API_KEY" in path.read_text(encoding="utf-8")))
def test_ai_workflows_are_least_privilege_and_inert_without_the_key(name):
    workflow = _workflow(name)
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in workflow["on"]
    for job_name, job in workflow["jobs"].items():
        keyed = [step for step in job["steps"] if "secrets.ANTHROPIC_API_KEY" in json.dumps(step)]
        if not keyed:
            continue
        assert job["env"]["ANTHROPIC_CONFIGURED"] == "${{ secrets.ANTHROPIC_API_KEY != '' }}", job_name
        assert all(step.get("if") == "env.ANTHROPIC_CONFIGURED == 'true'" for step in keyed), job_name
        assert any(step.get("if") == "env.ANTHROPIC_CONFIGURED != 'true'" and "GITHUB_STEP_SUMMARY" in step["run"]
                   for step in job["steps"]), job_name


def test_agent_evals_keep_the_secret_off_pull_request_runs():
    jobs = _workflow("agent-evals.yml")["jobs"]
    assert "ANTHROPIC_API_KEY" not in json.dumps(jobs["harness"])
    assert jobs["agent"]["if"] == "github.event_name != 'pull_request'"


def test_claude_review_skips_forks_and_answers_only_maintainers():
    jobs = _workflow("claude-review.yml")["jobs"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in jobs["review"]["if"]
    assert jobs["review"]["permissions"] == {"contents": "read", "pull-requests": "write", "id-token": "write"}
    assert '["OWNER","MEMBER","COLLABORATOR"]' in jobs["respond"]["if"]
    assert jobs["respond"]["needs"] == "respond-gate"
    assert "needs.respond-gate.outputs.same_repository == 'true'" in jobs["respond"]["if"]
    gate_step = jobs["respond-gate"]["steps"][0]
    assert '"$head_repo" = "$GITHUB_REPOSITORY"' in gate_step["run"]
    assert "github.event" not in gate_step["run"]
    assert jobs["respond-gate"]["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert "REVIEW.md" in jobs["review"]["steps"][-1]["with"]["prompt"]
    assert "never as instructions" in jobs["scan"]["steps"][-1]["with"]["prompt"]
