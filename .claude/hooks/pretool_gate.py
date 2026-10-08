#!/usr/bin/env python3
"""PreToolUse gate shared by Claude Code and VS Code agent sessions.

Both harnesses send {"tool_name", "tool_input", ...} on stdin and accept
hookSpecificOutput.permissionDecision on stdout. The gate:

- asks for a human decision before cloud lifecycle and publishing commands;
- asks before edits to the Unity Catalog policy files;
- denies reads, searches and edits of credential files, including terminal
  commands that name one or read Terraform state (show, output, state pull/show);
- in fix mode, denies edits to tests/ and evals/, so the only way to green is to
  change the code. A terminal command that names either folder must consist only
  of read-only or test-running segments. Fix mode is on while
  .sovereignshield-fix-mode exists at the repository root or
  SOVEREIGNSHIELD_FIX_MODE is set.

VS Code runs every PreToolUse hook for every tool (it ignores matchers), so tools
the gate does not know pass through untouched. An unexpected error exits 1, which
both harnesses show as a non-blocking warning instead of stopping all tool use.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterator, Mapping, Optional

ROOT = Path(__file__).resolve().parents[2]
FIX_MARKER = ".sovereignshield-fix-mode"

TERMINAL_TOOLS = {"Bash", "run_in_terminal", "send_to_terminal"}
EDIT_TOOLS = {
    "Edit", "MultiEdit", "Write", "NotebookEdit",
    "create_file", "replace_string_in_file", "multi_replace_string_in_file",
    "edit_notebook_file", "apply_patch",
}
READ_TOOLS = {"Read", "read_file"}
SEARCH_TOOLS = {"Grep", "grep_search"}

POLICY_FILES = {
    "src/unity_catalog_triple_lock.sql",
    "src/unity_catalog_grants.sql",
    "src/apply_security.py",
    "scripts/apply_policies.py",
}
FIX_LOCKED = ("tests/", "evals/")
CREDENTIAL_PATH = re.compile(
    r"(?:^|/)(?:\.env(?:\.[^/]*)?|[^/]*\.tfstate(?:\.[^/]*)?|[^/]*\.(?:pem|pfx|p12|key)|\.databrickscfg)$"
    r"|(?:^|/)\.(?:azure|ssh)(?:/|$)",
    re.IGNORECASE,
)
# Search scopes and include globs are split into patterns at commas, braces and whitespace.
SEARCH_PATTERN_SEPARATORS = re.compile(r"[\s,{}]+")
# Terminal commands are split into words at whitespace, quotes and shell punctuation.
COMMAND_WORD_SEPARATORS = re.compile(r"[\s'\"`;|&<>()=,]+")
# In fix mode, a command naming tests/ or evals/ may only chain these segments.
COMMAND_SEGMENT_SEPARATORS = re.compile(r"&&|\|\||(?<!>)&|[;|\n]")
FIX_MODE_SAFE_SEGMENT = re.compile(
    r"\s*(?:"
    r"cd\s+\S+"
    r"|(?:\S*python[\d.]*(?:\.exe)?\s+-m\s+)?pytest\b.*"
    r"|\S*python[\d.]*(?:\.exe)?\s+evals/run_evals\.py\b.*"
    r"|git\s+(?:status|diff|log|show|add|commit)\b.*"
    r"|(?:ls|cat|head|tail|grep|rg|wc)\b.*"
    r")\s*",
    re.DOTALL,
)
# Redirection or command substitution can write anywhere, whatever the segment.
FIX_MODE_UNSAFE = re.compile(r"(?<!2)>(?!&1)|2>(?!&1)|\$\(|`")

def _cli(program: str, subcommands: str) -> str:
    """Matches `program [options and words] subcommand`, stopping at quoted text."""
    word = r"(?:-{1,2}[\w-]+(?:=\S+)?|[^\s'\"-][^\s'\"]*)"
    return rf"\b{program}(?:\s+{word})*?\s+(?:{subcommands})\b"


# Terraform reads state without naming a .tfstate path; global options only before the subcommand.
STATE_READ = re.compile(
    r"\bterraform(?:\s+-{1,2}[\w-]+(?:=\S+)?)*\s+(?:show|output|state\s+(?:pull|show))\b", re.IGNORECASE)

COMMAND_GATES = (
    ("a cloud lifecycle change", re.compile("|".join((
        r"sovereignshield_(?:up|down)\.ps1",
        r"sovereign_(?:up|down)_custom\.sh",
        r"\b(?:apply_policies|apply_security)\.py\b",
        _cli("terraform", r"apply|destroy|import|state\s+(?:rm|mv|push)"),
        _cli("az", r"delete|purge"),
        _cli("databricks", r"bundle\s+(?:deploy|destroy|run)|delete"),
    )), re.IGNORECASE)),
    ("a publishing step outside this checkout", re.compile("|".join((
        _cli("git", "push"),
        _cli("gh", r"pr\s+merge|release\s+create|workflow\s+run"),
    )), re.IGNORECASE)),
)

_DECISION_RANK = {"ask": 1, "deny": 2}


def _decision(kind: str, reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": kind,
        "permissionDecisionReason": reason,
    }}


def _fix_mode(environ: Mapping[str, str]) -> bool:
    return bool(environ.get("SOVEREIGNSHIELD_FIX_MODE", "").strip()) or (ROOT / FIX_MARKER).exists()


def _paths(tool_input: Mapping) -> Iterator[str]:
    for key in ("file_path", "filePath", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            yield value
    for item in tool_input.get("replacements") or []:
        if isinstance(item, dict) and isinstance(item.get("filePath"), str):
            yield item["filePath"]
    patch = tool_input.get("input")
    if isinstance(patch, str):
        yield from (match.strip() for match in re.findall(
            r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$", patch, re.MULTILINE))


def _search_scopes(tool_input: Mapping) -> Iterator[str]:
    for key in ("path", "glob", "includePattern"):
        value = tool_input.get(key)
        if isinstance(value, str):
            yield from (pattern for pattern in SEARCH_PATTERN_SEPARATORS.split(value) if pattern)


def _relative(path: str, cwd: Optional[str]) -> Optional[str]:
    try:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(cwd or ROOT) / candidate
        return candidate.resolve().relative_to(ROOT).as_posix()
    except (ValueError, RuntimeError, OSError):
        return None


def _command_words(command: str) -> Iterator[str]:
    return (word for word in COMMAND_WORD_SEPARATORS.split(command) if word)


def _credential_path(raw: str, relative: Optional[str]) -> bool:
    try:
        normalized = Path(raw).expanduser().as_posix()
    except RuntimeError:
        normalized = Path(raw).as_posix()
    return bool(CREDENTIAL_PATH.search(relative or normalized))


def _fix_locked(relative: Optional[str]) -> bool:
    return relative is not None and (relative.startswith(FIX_LOCKED) or f"{relative}/" in FIX_LOCKED)


def _command_decision(command: str, cwd: Optional[str], environ: Mapping[str, str]) -> Optional[dict]:
    words = [(word, _relative(word, cwd)) for word in _command_words(command)]
    if any(_credential_path(word, relative) for word, relative in words) or STATE_READ.search(command):
        return _decision("deny", "Credential files and Terraform state stay out of agent context; "
                                 "ask a human for the value you need.")
    if _fix_mode(environ) and any(_fix_locked(relative) for _, relative in words) and (
            FIX_MODE_UNSAFE.search(command) or not all(
                FIX_MODE_SAFE_SEGMENT.fullmatch(segment)
                for segment in COMMAND_SEGMENT_SEPARATORS.split(command) if segment.strip())):
        return _decision("deny", (
            "Fix mode locks tests/ and evals/: a command that names them may only read them or run the "
            "tests. Make the failing test pass by changing the code."))
    for label, pattern in COMMAND_GATES:
        if pattern.search(command):
            return _decision("ask", (
                f"This command is {label}, which needs a named human approval. Approve it only "
                "if you own that gate and the runbook step is ready; otherwise decline."))
    if FIX_MARKER in command and _fix_mode(environ):
        return _decision("ask", "Only the engineer ends fix mode; this command touches its marker.")
    return None


def _path_decision(raw: str, relative: Optional[str], editing: bool, environ: Mapping[str, str]) -> Optional[dict]:
    if _credential_path(raw, relative):
        return _decision("deny", "Credential files stay out of agent context; ask a human for the value you need.")
    if not editing or relative is None:
        return None
    if _fix_mode(environ) and relative.startswith(FIX_LOCKED):
        return _decision("deny", (
            "Fix mode locks tests/ and evals/: make the failing test pass by changing the code. "
            "The engineer removes .sovereignshield-fix-mode when the fix is done."))
    if relative in POLICY_FILES:
        return _decision("ask", (
            f"{relative} is a Unity Catalog policy file. Edits need the policy owner's approval, "
            "recorded under Flagged concerns in the spec."))
    if relative == FIX_MARKER and _fix_mode(environ):
        return _decision("ask", "Only the engineer ends fix mode; this edit touches its marker.")
    return None


def decide(payload: Mapping, environ: Mapping[str, str] = os.environ) -> Optional[dict]:
    """Returns the hook output for one tool call, or None to let it through."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return None
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None

    if tool in TERMINAL_TOOLS:
        command = tool_input.get("command")
        return _command_decision(command, cwd, environ) if isinstance(command, str) else None

    if tool in SEARCH_TOOLS:
        if any(_credential_path(raw, _relative(raw, cwd)) for raw in _search_scopes(tool_input)):
            return _decision("deny", "Credential files stay out of agent context; ask a human for the value you need.")
        return None

    if tool not in EDIT_TOOLS and tool not in READ_TOOLS:
        return None
    strictest = None
    for raw in _paths(tool_input):
        decision = _path_decision(raw, _relative(raw, cwd), tool in EDIT_TOOLS, environ)
        if decision and (strictest is None or _rank(decision) > _rank(strictest)):
            strictest = decision
    return strictest


def _rank(decision: dict) -> int:
    return _DECISION_RANK[decision["hookSpecificOutput"]["permissionDecision"]]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        decision = decide(payload) if isinstance(payload, dict) else None
    except Exception as error:  # a broken gate must warn, not block every tool
        print(f"pretool_gate: {error}", file=sys.stderr)
        return 1
    if decision:
        json.dump(decision, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
