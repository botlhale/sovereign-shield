---
name: intent-capture
description: Turn a request, idea, incident, control-band breach or scan finding into a draft intent.md under intent/. Use when someone describes a problem or asks for a change and no intent folder exists for it yet.
---

# Intent Capture

Produces `intent/<YYYY-MM-DD>-<slug>/intent.md` from
[the template](../../../intent/_template/intent.md). An intent states the problem
and the outcome. It never prescribes the solution.

## Steps

1. Restate the request in one sentence. Ask the questions needed to fill each
   template section:
   - who is affected;
   - how the problem shows up today, with evidence;
   - what outcome would satisfy the requester;
   - what must not change.

   Ask before writing when any of these is unknown. Never invent evidence.
2. Check the [index](../../../intent/README.md) for an intent on the same problem.
   Extend that one instead of creating a duplicate.
3. Create the folder from today's date and a short kebab-case slug. Write
   `intent.md` with:
   - `Status: draft`;
   - the originator;
   - the product owner (@botlhale unless named otherwise);
   - the source (request, incident, control band or scan finding).
4. Keep solutions, file names and code out of *Problem* and *Proposed outcome*.
   Put known limits in *Constraints* and every unresolved point in *Open questions*.
5. Add the intent to the index with status `draft`.
6. Stop. Ask the product owner to answer the open questions and accept the intent.
   Do not start a spec until the status is `accepted`.

## Quality Bar

- The problem is observable and has evidence: a log line, a measurement or a report.
- The outcome can be checked by the requester without reading code.
- *Constraints* name the [reference contracts](../../../.github/skills/SKILLS.md)
  that apply.
