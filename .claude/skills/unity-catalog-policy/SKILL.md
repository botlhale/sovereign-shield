---
name: unity-catalog-policy
description: Rules for changing Unity Catalog row filters, column masks, grants, persona groups or policy deployment (the triple lock). Use before editing src/unity_catalog_triple_lock.sql, src/unity_catalog_grants.sql, src/apply_security.py, scripts/apply_policies.py, persona mappings, or the policy mirror used by the offline tests.
---

# Unity Catalog Policy

Read the contract that applies before changing anything. This skill points to the
contracts; it does not replace them.

- [Policy deployment contract](../../../.github/skills/triple_lock_security.md)
- [Persona and information-access contract](../../../.github/skills/persona_security_matrix.md)
- [External-provider workflow](../../../.github/skills/contractor_least_privilege_workflow.md)

## Rules

- **Approval.** The four policy files change only with the policy owner's
  approval, and the hooks ask before any edit. Record the approval under *Flagged
  concerns* in the spec.
- **Fail closed.**
  - A principal in no persona group sees zero rows.
  - Restricted values are NULL, never zero.
  - The key, lineage and value masks share their reveal branches.
- **Binding.** Never use `DROP ROW FILTER` or `DROP MASK` as an idempotency step.
  Rebind without detaching protection.
- **Change together.** Change the policy SQL, the local mirror (`LocalDeltaBackend`
  in `src/uc_query.py`, the personas in `tests/conftest.py`) and the portal as one
  change. Otherwise the live persona run fails.
- **Open decisions.** Do not change runtime permissions because a documentation
  review raises the open reconstruction decision.

## Checks

```bash
python -m pytest tests/test_persona_access_matrix.py tests/test_policy_deployment.py tests/test_contractor_isolation.py -p no:cacheprovider -o addopts=""
```

A live persona run (`pytest --live`) on a synthetic workspace is the acceptance
gate for a policy change. If it was not run, say so.
