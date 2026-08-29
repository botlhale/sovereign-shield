"""Zero-secret repository guarantee.

A leaked copy of this repository must not be a credential incident. That claim is
only worth making if something checks it on every change, so this scans the
working tree for material that should only ever exist in Azure Key Vault, in a
process environment variable, or in a platform-injected reference.

Detection is deliberately conservative about *shape* and strict about *placement*:
identifiers that are public by construction (a tenant domain, a first-party
Microsoft application id, a vault name) are allowed, while anything resembling a
usable secret is not.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest

SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".terraform",
    "node_modules", ".mypy_cache", ".ruff_cache", "local_delta_catalog",
}
SKIP_SUFFIXES = {".pdf", ".xls", ".xlsx", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".parquet"}

#: Public, non-sensitive identifiers that legitimately appear in configuration.
ALLOWED_LITERALS = {
    # First-party AzureDatabricks application id - a documented Microsoft constant.
    "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d",
    # user_impersonation scope id on that application.
    "739272be-e143-11e8-9f32-f2801f1b9fd1",
}

SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Azure storage connection string", re.compile(r"AccountKey=[A-Za-z0-9+/=]{20,}")),
    ("JDBC/ODBC password", re.compile(r"(?i)\b(?:pwd|password)=(?!\s*[\"']?\$)[^;\s\"']{4,}")),
    ("Databricks PAT", re.compile(r"\bdapi[0-9a-f]{32}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer token literal", re.compile(r"(?i)authorization\s*[:=]\s*[\"']bearer\s+[A-Za-z0-9._-]{20,}")),
]

#: Assignment of a credential-shaped name to a literal. A reference such as
#: os.getenv(...), $env:..., ${var...}, secretref: or keyvaultref: is the
#: correct pattern and is not a finding.
ASSIGNMENT = re.compile(
    r"(?i)(client_secret|clientsecret|api[_-]?key|apikey|secret_key|access_token|"
    r"sas_token|temp_password|password|passwd)"
    r"\s*[:=]\s*"
    r"[\"']([^\"'\n]{6,})[\"']"
)

REFERENCE_PREFIXES = (
    "$", "${", "os.", "secretref:", "keyvaultref:", "dbutils.", "<", "{{", "@",
)
REFERENCE_TOKENS = ("getenv", "environ", "keyvault", "secret_show", "var.", "data.", "example", "xxx", "changeme")

#: ${NAME:-default} and ${NAME:=default}. The whole expression starts with "$",
#: so a naive prefix check treats it as a safe reference - but the default is a
#: committed literal and is exactly where a hardcoded password hides.
SHELL_DEFAULT = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:[-=](.*)\}$")


def _candidate_values(value: str) -> Iterator[str]:
    """Yields the literal(s) an assignment actually commits to the file."""
    yield value
    default = SHELL_DEFAULT.match(value.strip())
    if default and default.group(1):
        yield default.group(1)


def _iter_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def _looks_like_reference(value: str) -> bool:
    lowered = value.lower()
    return (
        value.startswith(REFERENCE_PREFIXES)
        or any(token in lowered for token in REFERENCE_TOKENS)
        or value in ALLOWED_LITERALS
    )


@pytest.fixture(scope="module")
def tracked_files(repo_root) -> List[Path]:
    files = list(_iter_files(Path(repo_root)))
    assert files, "scanner found no files - the traversal is broken, not the repo clean"
    return files


def test_no_high_confidence_secret_material(tracked_files, repo_root):
    findings = []
    for path in tracked_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                if match.group(0) in ALLOWED_LITERALS:
                    continue
                line = text[: match.start()].count("\n") + 1
                findings.append(f"{path.relative_to(repo_root)}:{line} — {label}")

    assert not findings, "credential material in the working tree:\n  " + "\n  ".join(findings)


def test_credentials_are_referenced_never_assigned(tracked_files, repo_root):
    """A credential-shaped name must resolve at run time, not sit in the file."""
    findings = []
    for path in tracked_files:
        # This module necessarily contains the patterns it searches for.
        if path.name == Path(__file__).name:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in ASSIGNMENT.finditer(text):
            name, value = match.group(1), match.group(2)
            if all(_looks_like_reference(v) for v in _candidate_values(value)):
                continue
            line = text[: match.start()].count("\n") + 1
            findings.append(f"{path.relative_to(repo_root)}:{line} — {name} assigned a literal")

    assert not findings, "hardcoded credential(s):\n  " + "\n  ".join(findings)


def test_terraform_declares_no_secret_variables(repo_root):
    """Terraform reads secrets from Key Vault; it never accepts them as input.

    A ``variable "client_secret"`` would mean a value has to be supplied on the
    command line, in a tfvars file, or in CI settings - all places a credential
    must not be. The contractor declares *which* secret is needed; the
    environment resolves it in memory at apply time.

    A *pointer* to a secret is the opposite of a problem. Names ending in an
    identifier suffix carry a Key Vault resource id, which is what a
    ``keyvaultref`` needs and is not itself sensitive.
    """
    terraform = Path(repo_root) / "terraform"
    if not terraform.exists():
        pytest.skip("terraform/ not present")

    identifier_suffixes = ("_id", "_ids", "_uri", "_url", "_name", "_names", "_path")
    offending = []
    declaration = re.compile(
        r'variable\s+"([^"]*(?:secret|password|client_secret|token)[^"]*)"', re.IGNORECASE
    )
    for path in terraform.rglob("*.tf"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in declaration.finditer(text):
            name = match.group(1)
            if name.lower().endswith(identifier_suffixes):
                continue
            offending.append(f"{path.relative_to(repo_root)} — variable \"{name}\"")

    assert not offending, (
        "Terraform must look secrets up, not receive them:\n  " + "\n  ".join(offending)
    )


def test_terraform_never_writes_a_credential_to_an_output(repo_root):
    """A module output is readable via `terraform output` and lands in state.

    The proxy password is written to Key Vault and read from there by whatever
    needs it; it must never cross a module boundary as a value.
    """
    terraform = Path(repo_root) / "terraform"
    if not terraform.exists():
        pytest.skip("terraform/ not present")

    leaked = []
    block = re.compile(r'output\s+"([^"]+)"\s*\{(.*?)\n\}', re.DOTALL)
    for path in terraform.rglob("*.tf"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in block.finditer(text):
            name, body = match.group(1), match.group(2)
            if re.search(r"\.value\b|_password\b|\.password\b", body) and not name.lower().endswith(
                ("_id", "_ids", "_uri", "_url", "_name", "_names")
            ):
                leaked.append(f"{path.relative_to(repo_root)} — output \"{name}\"")

    assert not leaked, "credential exposed through an output:\n  " + "\n  ".join(leaked)


def test_no_tfvars_or_env_files_committed(tracked_files, repo_root):
    """These files exist to hold values that must never be committed."""
    forbidden = {".env", "terraform.tfvars", "terraform.tfstate"}
    found = [
        str(p.relative_to(repo_root))
        for p in tracked_files
        if p.name in forbidden or p.name.endswith(".tfstate.backup")
    ]

    assert not found, "value-bearing files present: " + ", ".join(found)


def test_pre_auth_resolves_secrets_by_name(repo_root):
    """Rotation must not require a code change.

    ``pre_auth.ps1`` looks secrets up by name, so rotating a credential in place
    keeps the pipeline working. It also discovers the vault by prefix — a
    hardcoded vault name silently breaks after re-provisioning, because the name
    carries a random suffix.
    """
    script = (Path(repo_root) / "sh" / "pre_auth.ps1").read_text(encoding="utf-8")

    assert "az keyvault secret show" in script
    assert "spn-client-secret" in script, "resolved by name"
    assert not re.search(r'KeyVaultName\s*=\s*"kv-sovereignshield-\d+"', script), (
        "vault name is hardcoded; it must be discovered by prefix"
    )
