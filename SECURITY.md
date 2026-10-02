# Security Policy

## Supported Versions

SovereignShield is a reference implementation rather than a versioned production product. Security fixes are made on the default branch. Older commits, forks, screenshots, exported demo data, and independently deployed environments are not maintained by the project maintainers.

| Version | Supported |
| --- | --- |
| Default branch | Yes |
| Older commits or forks | No |

## Reporting a Vulnerability

Use GitHub private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Select **Advisories**.
3. Select **Report a vulnerability**.

Do **not** disclose a suspected vulnerability in a public issue, pull request, discussion, screenshot, or demo artifact.

Include, where available:

- the affected file, component, endpoint, or deployment stage;
- the security boundary or persona involved;
- reproduction steps using synthetic data;
- the observed and expected behavior;
- potential impact and prerequisites;
- logs or request identifiers with credentials and personal data removed; and
- a proposed remediation or test case.

The project steward will assess the report, communicate through the private advisory, and coordinate remediation and disclosure as appropriate. No response-time or remediation-time service level is implied by this public repository.

## In Scope

Examples include:

- cross-persona or cross-jurisdiction data exposure;
- bypass of Unity Catalog row filters or column masks, including a withheld value whose exact coordinates or lineage hashes remain readable;
- secret leakage or unsafe credential handling;
- unauthorized deployment or privilege escalation;
- failure of the public tier to remain fail-closed;
- quarantine or SCD2 behavior that republishes rejected data; and
- malformed SDMX output that creates a security or integrity impact.

General bugs, documentation errors, feature requests, and deployment questions belong in public issue templates unless they disclose an exploitable weakness.

## Deployment Responsibility

This repository uses synthetic data and is not a production accreditation or managed service. Operators are responsible for threat modelling, privacy and legal review, identity governance, network design, monitoring, backup, recovery, and secure configuration of their own deployments. Public disclosure of this architecture does not grant access to any deployment operated by the author, maintainers, or another organization.

## Statistical Reconstruction Challenge

Row-level security and column masking enforce entitlements; they do not establish
statistical non-disclosure. Released totals, components, overlapping breakdowns,
time-series revisions and auxiliary public sources can reconstruct a withheld
measure. The synthetic fixture includes the exact residual $1000-400-500=100$.
Knowledge of the calculation method or the existence of a particular row can
make a masked value identifiable without bypassing any access-control function.

The Researcher persona is a Discovery Gateway. It exposes free observations in full
and, for restricted observations, the series family and reporting country (key
segments 1-9), the period and the confidentiality flag. Values, counterparty
coordinates (`xx.xx`) and lineage hashes are withheld, and downloads exclude those
rows. The remaining metadata, including how many restricted rows share a prefix, is
an information product requiring its own disclosure decision. Coordinate masking
does not stop a margin residual across visible dimensions: in the fixture the CA
claims total, domestic and foreign currency rows still give $1000-400-500=100$.
Community review of this **identified open challenge** is invited using synthetic
data. Document the released inputs, filters, units, time periods, equations or
linkage, inference confidence and affected personas. Do not probe third-party
deployments or use confidential source records.

Use a public issue for discussion of this already documented synthetic challenge.
Report a new exploitable access-control weakness through private vulnerability
reporting. Neither route grants authorization to test a live deployment.

Before production, the originating data authority and disclosure reviewer must:

1. Assess values, row presence, keys, counts, flags and revision differences across
	all released products and cumulative downloads, including public-only access.
2. Restrict or remove the Researcher role if identifying a row makes reconstruction
	trivial. A prefix-level discovery catalog that hides restricted-row counts, and a
	Secure Data Enclave for approved analysis, are design options, not implemented controls.
3. Validate secondary suppression, approved perturbation or a redesigned release
	product against the statistical utility and consistency requirements.
4. Re-run disclosure tests after every change to dimensions, release history,
	aggregation, personas or external linkage assumptions, and record release approval.

Removing the Researcher role does not repair inference possible from public totals.
The synthetic 0.60 dominance rule and educational bank micro-transaction ledger
illustrate classification only; they are not a complete disclosure methodology or
an international submission requirement.
