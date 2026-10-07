---
name: submission-history
description: Rules for the submission-aware Delta history (SCD2), replay, rejected and late arrivals, and the local demo catalog. Use before changing src/submission_history.py, src/spark_submission_history.py, src/local_pandas_scd2.py, sh/local_demo.py or the history columns.
---

# Submission History

Source of truth: [submission-aware Delta history contract](../../../.github/skills/scd2_engine.md).
The Analyst View rules are in the
[persona contract](../../../.github/skills/persona_security_matrix.md).

## Rules

- **One transaction per submission.** Each full submission is one MERGE. Never
  reintroduce separate expire, append or delete commits, or a year-9999 sentinel.
  An open `VALID_TO` is NULL.
- **Identity, not payload.** Replaying the same message adds nothing, and a new
  identical filing is kept. Identity is submission identity plus digest, never the
  payload hash alone.
- **Rejected and late arrivals.** These are audit rows. They never replace current
  accepted data.
- **Exact measures.** Measures are `DECIMAL(38,3)`, and a genuine zero is retained.
- **Legacy history.** History written with an older schema is never migrated or
  deleted implicitly. `sh/local_demo.py` stops with guidance, and only
  `--migrate-legacy` moves the old table aside.
- **Changes to `HISTORY_COLUMNS`.** These need the explicit migration gate in the
  [evidence register](../../../docs/RELEASE_EVIDENCE.md#mandatory-migration-gate).

## Checks

```bash
python -m pytest tests/test_submission_history.py tests/test_submission_scenarios.py -p no:cacheprovider -o addopts=""
```

A local pass is not evidence of production concurrency or throughput.
