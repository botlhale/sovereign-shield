---
name: cloud-lifecycle
description: How to change or run the Azure and Databricks lifecycle safely - sovereignshield_up.ps1, sovereignshield_down.ps1, the orchestration module, Terraform, the Asset Bundle and the bring-your-own-estate scripts. Use before editing sh/*.ps1, sh/lib/, terraform/, databricks.yml or scripts/, and before proposing any cloud run.
---

# Cloud Lifecycle

The [operations runbook](../../../docs/AUTOMATION_RUNBOOK.md) owns commands,
recovery and retention. The [resource provenance guide](../../../docs/RESOURCE_PROVENANCE.md)
explains why each resource exists.

## Running

- **Approval.** Cloud runs need a named human approval every time: up, down,
  `terraform apply/destroy`, Azure deletes and bundle deploys. The hooks ask.
  Propose the exact command and wait.
- **Runtime.** The greenfield scripts run in PowerShell 7 on Windows or Linux.
  Each prints per-step timings.
- **Resuming.** Resume a failed bring-up with `-StartAtStage`. Rerun down after a
  failure; it continues from whatever remains.

## Changing

- **Exit codes.** Check every native exit code.
  - `az ... wait` exits 0 on timeout, so re-check the state with a deadline.
  - CLI polling can stop before Azure finishes. Poll ARM until the resource is
    gone.
- **Extensions.** Install `az` extensions before first use
  (`Install-SovereignShieldAzExtension`). A hidden install prompt hangs captured
  output.
- **Portability.**
  - Resolve Python with `Get-SovereignShieldPython`.
  - Use `cmd.exe` or `.exe` paths only behind a Windows check.
  - Never hold the lifecycle lock while pytest runs: on Linux it is an flock.
- **Teardown order.** Delete Unity Catalog objects before their schemas and
  bundle resources before Terraform. Never delete what the bring-your-own scripts
  did not create.
- **Production.** Changes reach production only through `promote.yml` and its
  environment reviewers.

## Checks

```bash
python -m pytest tests/test_deployment_boundaries.py tests/test_custom_deployment.py tests/test_app_activation.py -p no:cacheprovider -o addopts=""
terraform -chdir=terraform fmt -recursive -check
pwsh -NoProfile -Command '$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("sh/sovereignshield_down.ps1",[ref]$null,[ref]$e); $e'
```

After a real run, add its recovery lessons to the runbook, and add a regression test
plus an eval case when it exposed a defect.
