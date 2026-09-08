# Runbook — pick a path

Two provisioning paths are supported. They are **alternatives, not a sequence**.

| | [Terraform](steps_terraform.md) | [Scripts](steps_scripts.md) |
| --- | --- | --- |
| Use when | Production, CI/CD, anything reproducible | A demo, a laptop, a first look |
| Provisions | Identity, workspace, catalog, warehouse, gateway | The same, imperatively |
| State | Remote `azurerm` backend | None |
| Re-run | `terraform apply` converges | Idempotent: prints `[skip]` / `[create]` |
| Teardown | `terraform destroy`, ordered | Manual `az` deletes, ordered |
| CI promotion | GitHub Actions via OIDC | Not provisioned |
| Cluster policy | Terraform-owned, pins `USER_ISOLATION` | Not provisioned |

**→ [steps_terraform.md](steps_terraform.md)** — the recommended path.

**→ [steps_scripts.md](steps_scripts.md)** — the quickstart.

Running both against one subscription is the one combination to avoid: the
scripts create resources Terraform did not create, and Terraform then has to
adopt them. If you started with the scripts and want to move to Terraform, set
`create_resource_group = false` and run `sh/terraform_reconcile.ps1` to import
what already exists.

---

**These are the *how*.** For the *why* — the contractor delivery pattern, the
ownership split between Terraform and the pipeline, the revocation model, and
where the model stops — read
[docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md](docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md).

To understand the codebase rather than deploy it, start with
[docs/technical_guide.md](docs/technical_guide.md).
