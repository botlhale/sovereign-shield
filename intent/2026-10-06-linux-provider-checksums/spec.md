# Spec: Lock the Terraform providers for Linux as well as Windows

- **Intent:** [intent.md](intent.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Approved by:** @botlhale, 2026-10-06
- **Skills applied:** `cloud-lifecycle`

## Requirements

- **R1.** The lock file gains the Linux `h1:` checksum of each of the five pinned
  providers. Versions, constraints and existing hashes are unchanged.

## Design

Commit the five checksums that `terraform init` added on Ubuntu, in a change of
their own.

## Flagged concerns

None.

## Acceptance criteria

- **R1:** The diff adds exactly five `h1:` lines. `terraform init -backend=false
  -lockfile=readonly` and `terraform validate` succeed on Linux.

## Out of scope

- Upgrading providers.
- Adding checksums for macOS.
