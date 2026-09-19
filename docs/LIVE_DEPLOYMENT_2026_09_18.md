# Live Deployment Recovery: 18 September 2026

This dated record covers Stage 6 timeout recovery and completion of one synthetic
deployment. It is separate from the [15 September evaluation](LIVE_DEPLOYMENT_2026_09_15.md).
The workload was left running at recovery handover and subsequently torn down by
the operator. The listed URLs identify that run, not a continuously available service.

## Failure and Repair

Stage 6 ran `databricks bundle run sovereignshield_portal` twice, assigning the
managed app identity to the public group between deployments. The second CLI
wait reported a timeout. The service subsequently reported both deployments as
`SUCCEEDED`, with the second active and no pending deployment:

- First deployment: `01f1b378d2d6119197d3e4e93f6b283e`.
- Second deployment: `01f1b378e9dd1d3784d6930bf04c05e8`.
- Active deployment created at `2026-09-18T15:52:12Z`, updated successfully at
  `2026-09-18T15:52:22Z`.

The repair assigns group membership before one snapshot activation and uses a
bounded SDK waiter. A Stage 6 resume reconciles the pending/latest deployment
instead of submitting another. It verifies the exact successful active deployment,
active compute, a running app and no pending replacement. Failed or cancelled
deployments remain failures. See the [resume procedure](AUTOMATION_RUNBOOK.md#resume-or-bound-a-run).

## Completed Stages

The manual `SovereignShield: resume app and gateway` task completed stages 6-8:

| Stage | Result | Observed duration |
| --- | --- | --- |
| 6 | Existing deployment reconciled successfully; no additional app deployment | 0.3 minutes |
| 7 | ACR build/push, Container Apps gateway, Key Vault references and Entra sign-in configured | 8.8 minutes |
| 8 | App status, five persona SQL entitlements, public fixture and Easy Auth gates passed | 1.0 minutes |

Total task elapsed time was 10.8 minutes, including state/output discovery.
Stages 0-5 were not rerun; no submission regeneration or infrastructure rebuild
was needed for this recovery.

## Recorded Endpoints

- Databricks App: <https://sovereignshield-portal-7405617422422154.14.azure.databricksapps.com>
- Public gateway: <https://ca-sovereignshield-portal.bravesand-f77ee01a.canadacentral.azurecontainerapps.io>
- Workspace: `7405617422422154`; SQL warehouse: `bbfc309868e6a55a`.
- Gateway image: `acrsovereignshield93647.azurecr.io/sovereignshield-portal:20260918124533`.
- Ready gateway revision: `ca-sovereignshield-portal--0000003`.
- Gateway state: `Succeeded` / `Running`; minimum and maximum replicas both 1.
- Registry pull uses the app's system identity. Easy Auth is enabled with
  `AllowAnonymous` and the Blob token store's `easy-auth-token-sas` reference.

## Verification and Limits

- Thirteen focused app-activation tests passed, covering single submission,
  stopped-compute startup, pending/successful recovery, failed/cancelled waits,
  timeout reconciliation, source mismatch and exact active-deployment checks.
- The offline pytest suite and both PowerShell regression scripts passed.
  Live persona tests and stress benchmarks were not rerun in this recovery.
- Public HTTP health and search returned 200 with 13 observations and no masked
  values. All rows were `PUBLISHED` / `F`, had three-place measures, and excluded
  submission IDs and source digests.
- Anonymous `lifecycle=quarantine` search and `lifecycle=all` audit export returned
  403. The API parameter is `lifecycle`; `view_mode` is an internal property.
- SDMx-ML, SDMx-JSON and SDMx-CSV each exported 13 observations. JSON passed the
  pinned official 2.0 schema; XML and CSV preserved three decimal places.
- Public browser checks at 1440x900 and 390x844 showed 13 rows, no page-width
  overflow and no external scripts.
- Databricks App platform checks passed and its browser URL reached workspace
  SSO. Azure CLI credentials alone received HTTP 401 at the App host. Human SSO
  and elevated-persona browser flows still require user verification; they are
  not claimed as tested here.

No teardown or push was part of the recovery task itself. Subsequent successful
script-driven provisioning and teardown were confirmed in the reference evaluation:
approximately 75 minutes up including prerequisites, 30 minutes down, and US$10 or
less in Azure charges for deploy/test/teardown. See [measurement scope](RELEASE_EVIDENCE.md#reference-evaluation-metrics);
those values are not the 10.8-minute partial recovery above or a production guarantee.

SDMx files are the modeled international input. Synthetic bank micro-transactions
remain educational calculation artifacts, not a system deliverable. The Analyst
View reconciles expected latest filings with receiver state. Researcher discovery
remains conditional on [disclosure assessment](../SECURITY.md#statistical-reconstruction-challenge).