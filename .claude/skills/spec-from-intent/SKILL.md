---
name: spec-from-intent
description: Write spec.md for an accepted intent by applying the domain skills and flagging policy concerns for their owners. Use when an intent has status accepted and the next step is requirements and design.
---

# Spec From Intent

Produces `spec.md` beside an accepted `intent.md`, from
[the template](../../../intent/_template/spec.md).

## Steps

1. Read the intent, its answered open questions, and the reference contracts its
   constraints name ([index](../../../.github/skills/SKILLS.md)).
2. Load each domain skill for an area the change touches, and list it under
   *Skills applied*:
   - `unity-catalog-policy`
   - `submission-history`
   - `sdmx-contract`
   - `evidence-and-claims`
   - `cloud-lifecycle`
3. Write numbered requirements (R1, R2, ...). Each one must be provable by a test, a
   command or a dated record.
4. Describe the design:
   - the components, data, contracts and interfaces it touches;
   - which existing mechanism it reuses, rather than adding a new one.
5. Put anything a skill cannot resolve, or anything that weakens a control, under
   *Flagged concerns*, naming the policy owner who decides. Never resolve a policy
   concern yourself.
6. Map every requirement to an acceptance check, and state what is out of scope.
7. Set the intent status to `specified` only once the product owner has approved
   the spec and every flagged concern has a resolution. Update the index.
