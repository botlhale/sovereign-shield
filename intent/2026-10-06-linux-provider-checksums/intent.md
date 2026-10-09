# Intent: Lock the Terraform providers for Linux as well as Windows

- **Status:** verified
- **Originator:** @botlhale, asking for every pending change to be committed
- **Product owner:** @botlhale
- **Date:** 2026-10-06
- **Source:** request

## Problem

`terraform/.terraform.lock.hcl` held `h1:` package checksums for Windows only. The
first `terraform init` on Ubuntu added the Linux checksums locally, which left the
file modified in every Linux checkout and was never committed.

## Proposed outcome

The committed lock file verifies the pinned provider packages on Linux and Windows,
so `terraform init` no longer modifies it on either platform.

## Affected users and systems

Operators and CI running Terraform on Linux; `terraform/.terraform.lock.hcl`.

## Constraints

- No provider version or constraint changes.

## Open questions

None.
