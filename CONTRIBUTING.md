# Contributing to SovereignShield

Thank you for helping improve SovereignShield. The project is developed in a personal capacity as an independent reference implementation for governed statistical-data platforms. Issues, documentation improvements, tests, and focused pull requests are welcome.

## Before You Start

- Search existing issues and pull requests before opening a duplicate.
- Open an issue before substantial architectural, dependency, data-model, or public API changes.
- Use GitHub private vulnerability reporting for security concerns; do not open a public security issue.
- Use synthetic data only. Never submit real client, institution, account, transaction, credential, or production metadata.
- Keep changes focused. A contribution should solve one clearly stated problem without unrelated cleanup.

## Local Setup

Python 3.12 is the CI reference version.

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe -m pytest tests/
```

On macOS or Linux, use `.venv/bin/python` and `.venv/bin/pip`.

The default suite is offline and requires no Azure or Databricks credentials. Tests marked `live` and `stress` run only when explicitly selected.

## Required Checks

Run the checks relevant to your change before opening a pull request.

```powershell
# Complete offline suite
.venv\Scripts\python.exe -m pytest tests/

# Terraform formatting and static validation
terraform -chdir=terraform fmt -recursive -check
terraform -chdir=terraform init -backend=false -input=false
terraform -chdir=terraform validate
```

Changes to Databricks bundle resources should also pass `databricks bundle validate` in an authorized development workspace. Do not use production credentials to validate a community contribution.

## Security and Data Rules

SovereignShield is intentionally fail-closed. Contributions must preserve these invariants:

- a principal in no recognized persona group sees zero rows;
- the public tier is an explicit service principal and group, not anonymous fall-through;
- reporting-country sovereignty is derived from segment 9 (`L_REP_CTY`) of the SDMX key;
- restricted values are absent or `NULL`, never replaced with zero;
- quarantined revisions cannot replace the last valid published version;
- no secret, token, private key, backend configuration, state file, or real institutional data is committed; and
- table policies remain enforced in Unity Catalog rather than being duplicated only in application code.

A security-sensitive change should include a regression test that fails when the control is removed or inverted.

## SDMX and Validation Changes

When changing structures, serializers, codelists, or consistency rules:

- cite the authoritative standard or published artifact in the pull request;
- preserve the eleven-dimension BIS LBS key order;
- add a round-trip or schema-validation test for outbound formats;
- distinguish format compliance from business-rule validation; and
- do not transcribe a published rulebook into code when it can be parsed directly.

## Pull Requests

A useful pull request:

1. explains the problem and why the proposed behavior is correct;
2. identifies affected security, data, deployment, or standards boundaries;
3. includes focused tests and relevant documentation updates;
4. reports commands run and their results; and
5. contains no generated environment files or unrelated formatting churn.

Maintainers may ask for changes or decline a proposal that expands operational scope, weakens a security invariant, duplicates an existing mechanism, or does not fit the reference architecture.

## Licensing and Commercial Support

Unless explicitly stated otherwise, contributions intentionally submitted for inclusion are licensed under the [Apache License 2.0](LICENSE), consistent with section 5 of that license.

Participation in this repository does not create a client, employment, support, warranty, or procurement relationship with the author, maintainers, or copyright holders. Production implementation, institutional assessment, and contracted support are separate engagements from community contribution review.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
