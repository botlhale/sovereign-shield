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
- bypass of Unity Catalog row filters or column masks;
- secret leakage or unsafe credential handling;
- unauthorized deployment or privilege escalation;
- failure of the public tier to remain fail-closed;
- quarantine or SCD2 behavior that republishes rejected data; and
- malformed SDMX output that creates a security or integrity impact.

General bugs, documentation errors, feature requests, and deployment questions belong in public issue templates unless they disclose an exploitable weakness.

## Deployment Responsibility

This repository uses synthetic data and is not a production accreditation or managed service. Operators are responsible for threat modelling, privacy and legal review, identity governance, network design, monitoring, backup, recovery, and secure configuration of their own deployments. Public disclosure of this architecture does not grant access to any deployment operated by the author, maintainers, or another organization.
