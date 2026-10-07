# Plan: Lock the Terraform providers for Linux as well as Windows

- **Spec:** [spec.md](spec.md)
- **Author:** GitHub Copilot (Claude Opus 5.5)
- **Date:** 2026-10-06
- **Accepted by:** @botlhale, 2026-10-06

## Files that change

| File | Change |
| --- | --- |
| `terraform/.terraform.lock.hcl` | Five added `h1:` checksums |

## Order of work

1. Confirm that the diff adds only checksums.
2. Verify with a read-only lock, then commit.

## Risks

| Risk | Mitigation |
| --- | --- |
| A provider version changes unnoticed | The diff is checked for `version` and `constraints` lines before commit |

## Proof

```bash
git diff terraform/.terraform.lock.hcl
terraform -chdir=terraform init -backend=false -input=false -lockfile=readonly
terraform -chdir=terraform validate
```

## Rollback

Revert the commit; Terraform re-adds the checksums locally on the next Linux init.

## Evidence

Verified on 6 October 2026 on Ubuntu with Terraform 1.16.4:

- The diff adds five `h1:` lines (databricks, azuread, azurerm, random, time) and
  changes no `version` or `constraints` line.
- `terraform init -backend=false -lockfile=readonly` succeeded and `terraform
  validate` reported "Success! The configuration is valid."
