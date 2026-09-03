# SovereignShield — Public Write-Up

Three copy-paste-ready LinkedIn posts, plus the reasoning behind naming the
actual technology stack.

* [Naming the stack — what is safe and what is not](#naming-the-stack)
* [Version 1 — The Contractor Dilemma](#version-1--the-contractor-dilemma) (SLT-lead, flagship)
* [Version 2 — The Bug My Test Missed](#version-2--the-bug-my-test-missed) (hook-lead, more technical)
* [Version 3 — Short](#version-3--short) (feed-friendly)
* [Comment reply for the inevitable question](#comment-reply)
* [Before you post](#before-you-post)

Attach `sovereign-shield_executive.jpg` to whichever you choose.

---

## Naming the stack

Your instinct is right: "a cloud data platform" persuades nobody. Naming Azure
Databricks, Unity Catalog, Entra ID, Key Vault and pysdmx is what makes the post
checkable — and checkable is what makes it credible.

It is also legally routine, provided you stay on the right side of one line.

### The line

**Nominative use** — naming a product to describe what you actually used — is
lawful and needs no permission. What is not lawful is implying **affiliation,
endorsement, sponsorship or certification**.

| Safe | Not safe |
| --- | --- |
| "Built on Azure Databricks and Unity Catalog" | "Microsoft-approved", "Databricks-certified", "in partnership with…" |
| "Serialised with pysdmx" | "An official SDMX toolkit" |
| "Inspired by the BIS Data Explorer" | "A BIS system", "developed for the BIS" |
| Product names as plain text | Any rendered logo or brand mark |
| Describing what the tool does | Suggesting the vendor reviewed or blessed your work |

### pysdmx specifically

Worth knowing before you name it: **pysdmx is maintained by the BIS itself**
(`github.com/bis-med-it/pysdmx`, Apache-2.0, authored from a `bis.org` address).

That cuts both ways. It strengthens the post — you used the standards body's own
library rather than hand-rolling the format. It also **raises the bar on the
disclaimer**, because a reader could slide from "uses the BIS library" to "is a
BIS project" without noticing.

Apache-2.0 §6 is explicit that the licence grants **no trademark rights**. So:
use the name to *describe a dependency*, never as a badge.

This is why all three versions below carry the non-affiliation statement in the
post body, not only inside the image.

### The BIS Data Explorer

Naming a public website as design inspiration is fine. The failure mode is not
trademark — it is a reader assuming you had access to real submissions. Every
version therefore says "synthetic" explicitly and early.

### The risk that actually bites

Not trademark. **Employment.** If you have an employer, check your contract for
IP-assignment and outside-work clauses before publishing a portfolio project,
and make sure nothing in the post implies your employer built, endorsed or
sponsored it. That is the exposure most people overlook while worrying about
logos.

Not legal advice. If you have counsel, a two-minute read is cheap insurance.

### Two LinkedIn mechanics

**Do not @-tag the company pages.** A tag creates an association signal and can
pull a brand-monitoring team into your comments. Plain text mentions do not.

**LinkedIn does not render Markdown.** No `**bold**`, no `# headings`, no
`[text](url)` — they appear literally. The versions below are plain text and are
meant to be copied exactly as they are. Unicode "bold" characters are avoided
deliberately: screen readers skip or spell them out.

---

## Version 1 — The Contractor Dilemma

**~2,750 characters. SLT-lead, roughly 70/30. This is the flagship.**

```text
The people you need for specialist data work are, almost by definition, the people who shouldn't have the data.

That's not a hiring problem. It's an architecture problem.

Every quarter, national authorities send confidential banking statistics to international bodies. Three obligations apply at once, and they pull against each other:

→ Sovereignty. A country's detailed figures are its own. Not visible to another country, even inside a shared system.
→ Confidentiality. Some figures could identify a single institution. Withheld from researchers, without breaking the surrounding structure.
→ Integrity. Nothing internally inconsistent gets published. Not the inconsistent part — none of it. The totals that reconcile depend on the components that didn't.

Institutions uphold all three today, rigorously, with mature software and decades of protocol. I'm not proposing a replacement.

I spent a few weeks on an adjacent question: what if those obligations were properties of the platform itself, rather than rules the application is trusted to follow?

So I built it.

Azure Databricks and Unity Catalog hold the rules. Not the application — the catalogue. A row filter and a column mask are attached to the table, resolved against Microsoft Entra ID per caller, per row, at query time. Delta Lake keeps full history. Credentials live in Azure Key Vault and are never written to disk. Terraform provisions it; GitHub Actions deploys via OpenID Connect, so no secret is stored anywhere.

The submissions themselves are real SDMX 3.0, serialised with pysdmx — the BIS's own open-source library — against the genuine published Locational Banking Statistics structure. The validation rulebook is parsed at runtime from the published workbook, so a standards revision needs no code change. The portal is modelled on the BIS Data Explorer.

Four audiences query the same table and get four different answers. Public sees published figures. Researchers see everything published, with sensitive values blank. A national analyst sees their own jurisdiction in full. An auditor sees all of it.

A fifth case matters more than those four. Someone in none of those groups sees zero rows. Not an error. Nothing.

Which means off-boarding a contractor and enforcing sovereignty between two nations are the same mechanism. There's no separate revocation feature to forget.

And it was built without the data. Specification in, working platform out. Every test runs on a laptop with no cloud credentials.

A leaked copy of that repository isn't a data incident. There's no credential and no observation in it.

Independent reference architecture. 100% synthetic data. Not affiliated with or endorsed by the BIS, any central bank, or any vendor named above.

Repository in the comments. I'd genuinely like to be told where this breaks.
```

---

## Version 2 — The Bug My Test Missed

**~2,850 characters. Hook-lead, closer to 50/50. Use this if your audience skews
technical, or as a follow-up to Version 1.**

> **Accuracy note.** This describes a defect written and caught **during
> development**, on synthetic data, before anything was deployed to anyone. Say
> "wrote" and "caught", never "shipped" — shipped implies it reached a user, and
> a reader who later discovers otherwise loses trust in the whole post. The
> honest version is also the better story: the controls caught it.

```text
I wrote a data-sovereignty bug that would have let any national analyst read every other country's confidential figures.

Then I wrote a test for it that passed anyway.

Both were caught in development, on synthetic data, before any of it was deployed. That's the point of the story, not a footnote to it.

Context: I've been building a reference architecture for confidential statistical exchange — the quarterly submission of national banking statistics to an international body. The question I was chasing is whether sovereignty, confidentiality and integrity can be properties of the data platform rather than rules the application is trusted to follow.

The stack: Azure Databricks with Unity Catalog holding the policy, Microsoft Entra ID resolving identity, Delta Lake keeping history, Azure Key Vault holding credentials, Terraform provisioning it, and pysdmx — the BIS's own open-source library — producing genuine SDMX 3.0 messages against the published Locational Banking Statistics structure.

Entitlement is a row filter plus a column mask, attached to the table, evaluated per caller and per row at query time.

Here's the bug.

The column mask decided whether to hide a value based on the confidentiality flag and the caller's group. That reads as correct. It isn't. It knows a value is confidential, but not whose it is — so any national analyst would have unmasked every jurisdiction's restricted figures, not just their own.

The fix was to pass the series key into the mask, so it re-checks the reporting country rather than trusting the group name.

Here's the worse part.

My test for that fix passed against a completely broken mask. The row filter had already removed those rows before the mask ran, so the assertion was vacuous — it asserted something that was true for the wrong reason.

I only found out by deliberately putting the bug back to watch the suite go red. It didn't.

A test you have never watched fail is a test you have not written.

Two more things I'd have got wrong without building it:

A rejected submission has to degrade to stale data, never missing data. The previously published figure stays live and the rejection is recorded for audit. Get this wrong and it doesn't throw an error — it quietly deletes a published series.

And a fixture with one country cannot catch a cross-border leak. The bug above is undetectable unless your test data has confidential rows in more than one jurisdiction.

The whole thing runs on synthetic data and was built without access to anything real. Every test runs offline with no cloud credentials, which is the point: the person building it never needs to hold what it protects.

Independent reference architecture. 100% synthetic data. Not affiliated with or endorsed by the BIS, any central bank, or any vendor named above.

Repository in the comments. Tell me what else is wrong with it.
```

---

## Version 3 — Short

**~1,250 characters. For a busy feed, or as a comment under someone else's post
about data sovereignty.**

```text
The people you need for specialist data work are, almost by definition, the people who shouldn't have the data.

I spent a few weeks treating that as an architecture problem rather than a hiring one.

The setup: confidential national banking statistics, submitted quarterly to an international body. Sovereignty, confidentiality and arithmetic integrity all apply at once, and they pull against each other.

The approach: put the rules in the catalogue instead of the application. Azure Databricks and Unity Catalog hold a row filter and a column mask, resolved against Microsoft Entra ID per caller, per row, at query time. Real SDMX 3.0 messages via pysdmx, the BIS's own open-source library. Portal modelled on the BIS Data Explorer.

Four audiences query the same table and get four different answers. A fifth case matters more: someone in no group sees zero rows. Not an error — nothing.

So off-boarding a contractor and enforcing sovereignty between two nations run through the same mechanism. No separate revocation feature to forget.

And it was built without the data. Every test runs on a laptop with no cloud credentials. A leaked copy of the repo isn't a data incident.

Independent reference architecture, 100% synthetic data, not affiliated with any organisation named. Repository below.
```

---

## Comment reply

Someone will ask whether it's in production. Have this ready.

```text
No — and I'd be sceptical of anyone claiming otherwise on a first pass at this.

It's a working reference architecture running the genuine published validation rulebook and real SDMX 3.0 message structures against generated submissions. What it demonstrates is that the controls can be expressed as platform constraints rather than application logic.

Because they're attached to catalogue objects rather than embedded in pipeline code, they activate on real data at first run. There's no "productionisation" phase where the security model gets re-implemented, and therefore no phase where it can be re-implemented incorrectly.

What it does not demonstrate is behaviour at real volume. That needs a production dry-run I haven't done.
```

---

## Before you post

- [ ] Repository public, README disclaimer visible without scrolling
- [ ] Every claim traces to something in the repository
- [ ] Non-affiliation and synthetic-data statement present in the post body
- [ ] No employer, client or institution named or implied
- [ ] No company pages @-tagged
- [ ] Repository link posted as the **first comment**, not in the body — LinkedIn
      suppresses reach on posts with outbound links
- [ ] Employment agreement checked for IP-assignment and outside-work clauses
- [ ] Ready for "is this production?" within the first hour

**On the first two lines.** LinkedIn truncates at roughly 140–210 characters on
mobile. Versions 1 and 3 open on the contractor paradox and Version 2 on the
defect caught in testing, because both are complete thoughts that survive
truncation. An
opening like "Excited to share…" spends that budget on nothing.

**On tone.** The credibility of this rests on the limitations, not the
achievements. People who have worked in statistical exchange have decades on
this and will spot overreach instantly. Naming the defect you wrote and caught,
and the test that failed to catch it, is what earns the rest a fair hearing.

**On precision about that defect.** It was written and caught in development, on
synthetic data, before any deployment. Never say "shipped", "in production" or
"a customer found" — all three are false, and being caught embellishing a bug
story costs more credibility than the bug story earns. The accurate account is
stronger anyway: the fixture design and the mutation check are what found it.
