# Submission-Aware Delta History Contract

Use this reference when modifying replay, revisions, ordering or persistence.
The owners are [submission_history.py](../../src/submission_history.py),
[spark_submission_history.py](../../src/spark_submission_history.py) and
[scd2_merge_engine.py](../../src/scd2_merge_engine.py).

## Input Boundary

The international intake is **SDMx files only**. Synthetic bank micro-transactions
are educational artifacts illustrating how realistic observations are calculated;
the separately protected demo ledger is not an international intake requirement
or a system deliverable. The macro writer validates the submitted SDMx values,
not a recomputation from that ledger.

## Identity and Scope

- One immutable `SUBMISSION_ID` identifies a nonempty full
  country/period/aggregation snapshot.
- The observation key is `TIME_SERIES_CODE`, `DATE`, `AGG_CODE`.
- `RECORD_ID` includes submission identity plus the observation key.
- `SOURCE_SHA256` and validation/content checks detect altered reuse of an ID.
  `version_hash` is not a replacement for filing identity.
- `SUBMITTED_AT` is sender-reported; `RECEIVED_AT` is processing time. Production
  requires an approved trusted receipt/sequence and clock-skew contract.

## One Transaction per Submission

| Arrival | Transition |
| --- | --- |
| Same message and content replayed | No duplicate rows and no new history commit |
| Newer accepted full snapshot | Close all current rows in its exact scope and insert the complete replacement in one Delta MERGE |
| Smaller accepted replacement | Close omitted keys as part of the same scope transition |
| New accepted filing with identical values | Retain new filing identity; close prior current scope and insert new current snapshot |
| Rejected filing | Insert closed audit rows only; leave current accepted state unchanged |
| Older accepted filing arriving late | Retain audit-only; do not displace a newer accepted submission |
| Reused ID with altered content, duplicate keys, empty or unsupported action | Refuse the input |

Open current intervals use `VALID_TO=NULL`. Closed rejected/late audit-only rows
have `VALID_TO=VALID_FROM`. Measures use `DECIMAL(38,3)`; genuine zero is retained.
Do not reintroduce separate expire/append/delete commits, a year-9999 sentinel,
or payload-only deduplication that loses distinct identical filings.

The Spark adapter stages close/insert operations and performs one native SQL
MERGE through a temporary view. Local delta-rs uses the same information contract
and a single table merge. The educational ledger and macro history are separate
transactions; deterministic ledger IDs enable repair, not multi-table atomicity.

## Analyst Reconciliation

The Analyst View allows submitters to compare their expected latest filing with
actual receiver IDs, timestamps, values and acceptance feedback. The portal's
current publication and quarantine modes distinguish latest submitted from
current accepted data. Historical accepted versions remain available through
authorized history queries, not standard SDMx feeds.

## Concurrency and Recovery

The bundle runs one ingestion job at a time. A file lock coordinates cooperating
local writers; neither mechanism serializes independent deployments or privileged
external writers. Restrict mutation rights and test distributed conflicts in the
target environment. Repair failed tasks against archived arrivals; generating
new files creates new identities and is not replay.

The policy executor creates/verifies protected target schemas before ingestion.
Incompatible legacy history requires the [explicit migration gate](../../docs/RELEASE_EVIDENCE.md#mandatory-migration-gate).
No teardown or destructive migration is implicit in this contract.

## Verification

[History tests](../../tests/test_submission_history.py) cover replay, smaller
replacements, rejected/late arrivals and identity refusal.
[Live acceptance](../../src/live_runtime_checks.py) exercises actual Delta and
UC behavior. A local pass is not production concurrency or throughput evidence.

The state-transition principles are technology-agnostic. Terraform-supported
alternative stacks require equivalent transactional and identity adapters;
Delta/UC behavior must not be assumed for AWS, GCP, Fabric or open-source ports.