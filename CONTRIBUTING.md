# Contributing to SovereignShield

SovereignShield is developed in a personal capacity and shared for educational purposes as an independent reference implementation for governed statistical-data platforms. Issues, documentation improvements, tests, focused pull requests, synthetic reconstruction attempts, and lessons from ports to other platforms are welcome.

## Before You Start

- Search existing issues and pull requests before opening a duplicate.
- Open an issue before substantial architectural, dependency, data-model, or public API changes.
- Use GitHub private vulnerability reporting for security concerns; do not open a public security issue.
	Discussion of the already documented synthetic [reconstruction challenge](SECURITY.md#statistical-reconstruction-challenge)
	can use a public issue; new exploitable weaknesses remain private reports.
- Use synthetic data only. Never submit real client, institution, account, transaction, credential, or production metadata.
- Keep changes focused. A contribution should solve one clearly stated problem without unrelated cleanup.

## Local Setup

Python 3.12 is the CI reference version.

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

The default suite is offline and requires no Azure or Databricks credentials. Tests marked `live` and `stress` run only when explicitly selected.

## Required Checks

Run the checks relevant to your change before opening a pull request, from the activated environment.

```bash
# Complete offline suite
pytest

# Documentation links; add --render-diagrams after editing docs/figures/*.svg (needs Chrome or Chromium)
pip install -r sh/requirements-docs.txt
python sh/verify_docs.py

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
- reporting-country sovereignty is derived from segment 9 (`L_REP_CTY`) of the SDMX key, stored as the unmasked `L_REP_CTY` column that every Unity Catalog policy reads, since a masked column cannot be another policy's input;
- restricted values are absent or `NULL`, never replaced with zero;
- quarantined revisions cannot replace the last valid published version;
- no secret, token, private key, backend configuration, state file, or real institutional data is committed; and
- table policies remain enforced in Unity Catalog rather than being duplicated only in application code.

A security-sensitive change should include a regression test that fails when the control is removed or inverted.

The modeled international intake is SDMx files only. Synthetic bank micro-transactions
are educational calculation fixtures, not institutional submissions or a required
system deliverable. Preserve the Analyst View's distinction between expected latest
filings, actual receiver state and current accepted publication.

Researcher-visible row existence and public totals may reconstruct masked values.
The researcher persona is a Discovery Gateway: restricted rows keep segments 1-9 of
the key and show `xx.xx` for the counterparty, with value and lineage columns NULL.
Preserve that reveal rule in the mask functions, the local mirror and the portal.
Synthetic community tests are welcome; restrict or remove the Researcher role in
a production design if row presence makes inference trivial. Runtime policy changes
require explicit review, not just a documentation change.

## SDMX and Validation Changes

When changing structures, serializers, codelists, or consistency rules:

- cite the authoritative standard or published artifact in the pull request;
- preserve the eleven-dimension BIS LBS key order;
- add a round-trip or schema-validation test for outbound formats;
- distinguish format compliance from business-rule validation; and
- do not transcribe a published rulebook into code when it can be parsed directly.

Interpretation of rule metadata remains code requiring independent review. Treat
Terraform-supported AWS, GCP, Fabric and open-source extensions as new implementations
with equivalent acceptance tests, not automatically portable controls.

## Documentation Changes

Use objective architectural statements, one shared title for the Executive Brief
and White Paper, and the [evidence register](docs/RELEASE_EVIDENCE.md) for measured
results and limitations. Preserve dated historical findings as historical; do not
turn a bounded synthetic cost/timing observation into a production guarantee.
State each limitation once in its owning document and link to it. Run the
documentation contract tests and `sh/verify_docs.py`; proof both publications
after changes to content, figures or page layout.

## AI-Assisted Software Development Life Cycle

Generative AI coding assistants were used throughout this project as an engineering
accelerator, in the same way a team uses code generators, linters and templates.

| AI accelerated | Senior engineering owned |
| --- | --- |
| Boilerplate scaffolding for scripts, tests, Terraform modules and documentation | Architecture: planes, trust boundaries, persona model and ownership split |
| SDMx 3.0 structure mapping from the pinned BIS LBS DSD and codelists | Mathematical disclosure rules: reveal conditions, coordinate masking, the reconstruction challenge |
| Synthetic fixture generation and failure-injection cases | Security controls: policy SQL, deployment verification, side-channel review and teardown safety |
| Diagram drafts and image-generation prompts | Final wording, figures and every published claim |

Every AI-assisted change passes the same gates as hand-written code: review against
the [reference contracts](.github/skills/SKILLS.md), credential-free tests that fail
when a control is removed, documentation contract checks and, for controls, live
acceptance on a synthetic workspace. AI output is never evidence on its own: a
generated claim is accepted only when a test, a dated live record or a cited
standard supports it. No confidential, client or production data is given to AI
tools; prompts use synthetic fixtures and public standards only.

Contributors may use AI tools under the same rules. Disclose substantial AI
assistance in the pull request, review every line you submit, and never paste
secrets, tokens or non-public institutional material into a prompt.

## Pull Requests

A useful pull request:

1. explains the problem and why the proposed behavior is correct;
2. identifies affected security, data, deployment, or standards boundaries;
3. includes focused tests and relevant documentation updates;
4. reports commands run and their results; and
5. contains no generated environment files or unrelated formatting churn.

Maintainers may ask for changes or decline a proposal that expands operational scope, weakens a security invariant, duplicates an existing mechanism, or does not fit the reference architecture.

## Licensing and Collaboration

Unless explicitly stated otherwise, contributions intentionally submitted for inclusion are licensed under the [Apache License 2.0](LICENSE), consistent with section 5 of that license.

Participation in this repository does not create a client, employment, support, warranty, or procurement relationship with the author, maintainers, or copyright holders. The repository is educational material, not a service offering. Proposals for research collaboration, co-authoring, talks, or independent review are welcome through the channels listed under [Learn, Challenge and Collaborate](README.md#learn-challenge-and-collaborate) and remain separate from community contribution review.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
