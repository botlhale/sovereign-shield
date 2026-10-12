# LinkedIn First Post: Copy-Ready Text

The first publication in the [LinkedIn publication plan](LINKEDIN_POST.md) is the anchor
article, shared to the feed with a short introduction. This page holds both, ready to paste.
Clear every [gate before posting](LINKEDIN_POST.md#gates-before-posting) first.

| Step | Where | What to paste |
| --- | --- | --- |
| 1 | Home > **Write article** | Part A: headline, then body |
| 2 | Article **Publish** dialog, "Tell your network what your article is about" | Part B |

**How to copy.** LinkedIn does not render Markdown.

- **Part A (article):** open this file in the rendered GitHub view and copy from the
  rendered text, so headings, bold and numbered lists carry over into the article editor.
  Paste the headline into the title field separately.
- **Part B (feed text):** copy the contents of the text block. The feed keeps line breaks
  but no formatting.

**Images.** Cover image: [four audiences, one governed source](figures/ai/four_audiences.jpg).
Inline images where marked: the [Discovery Gateway capture](../demo/researcher_discovery_view.png)
and the [triple-lock illustration](figures/ai/triple_lock_illustration.jpg). Caption both
generated images "AI-generated illustration".

**Figures quoted.** Bring-up and teardown times, Azure charges and the offline test count
come from the [evidence register](RELEASE_EVIDENCE.md). Recheck them against the frozen
commit before posting.

---

## Part A: Article

**Headline**

```text
Build without seeing: how contractors and AI agents can engineer a statistical data platform without touching confidential data
```

**Body**

My work has long sat where data governance meets international statistics: group-based
row-level security for regulatory returns on a commercial cloud platform, and a banking
statistics pipeline modernized to produce SDMX 3.0. At SDMX community events, three
conversations kept coming back.

- **Executives** want masking they can trust: not "the developer promises not to look", but
  controls no developer can talk their way around.
- **Data holders** want to work with researchers without handing over the data.
- **Reporting analysts** who file several submissions want a simple answer: which copy does
  the international organization actually hold?

International organizations often build their SDMX stacks on open source, while many
central banks run on a commercial cloud. I wanted to see what the same controls look like
on Azure Databricks, so I built Sovereign Shield: an independent reference architecture on
synthetic data only, with the code, evidence and limits published so others can study,
reuse and challenge it.

### The contractor dilemma

Statutory confidentiality says contributors' data is used for statistics and released only
when no one can be identified. Yet the engineering that enforces it (Unity Catalog
policies, Delta Lake history, SDMX serialization, Terraform) is increasingly delivered by
integrators, contractors and AI coding agents. Giving builders production access in order
to build the controls that protect production is a contradiction.

### The pattern: build without seeing

1. **Contract, not data.** The data owner approves metadata only: the BIS LBS 1.0
   structure, codelists, 21 validation rules and a persona matrix. Builders generate
   synthetic SDMX filings that exercise every branch.
2. **Policies travel with the table.** Unity Catalog row filters and column masks decide
   per caller, per row and per cell. The same SQL runs in staging and production.
3. **Prove it offline.** More than 240 credential-free tests fail if a control is removed.
4. **Hand over and revoke.** The institution imports a reviewed release, owns every
   identity and offboards the builders.

Four personas read one governed store:

- the **public** sees free values;
- **submitting analysts** see their own filings in every state, so they can reconcile what
  they sent with what the receiver holds;
- **administrators** see the full audit trail;
- and **researchers** get something new.

*[Inline image: Discovery Gateway capture]*

### The idea I most want feedback on: a Discovery Gateway

A researcher should be able to discover that confidential data exists, so they can
approach the submitting central bank, without learning the value or even exactly what it
describes. For restricted cells the platform withholds the value and masks the
counterparty:

**Q.S.C.A.USD.D.5J.A.US.A.5J** becomes **Q.S.C.A.USD.D.5J.A.US.xx.xx**

Masked rows never appear in a download, so a researcher's export is identical to the
public one.

*[Inline image: triple-lock illustration, captioned "AI-generated illustration"]*

### Two lessons that surprised me

**Masking a value is not enough if you leave its fingerprints.** A row hash built from the
full key can be brute-forced back to hidden coordinates in a few thousand guesses, and a
payload hash confirms a guessed value. Both are now masked by the same rule.

**Masks must resolve before filters**, or a researcher can filter by counterparty and watch
which restricted row appears. Unity Catalog applies masks first, and the tests hold the
local mirror to the same rule.

### What it does not solve

Access control is not disclosure control. In the synthetic data, a published total of
1,000 minus public components of 400 and 500 still reveals a restricted cell of 100,
masked coordinates or not. That needs complementary suppression decided by the data
authority. Researchers who genuinely need restricted cells belong in a secure enclave:
approved projects, no raw export, reviewed outputs. That part is a concept, not code.

### Beyond statistics

The same question now faces AI assistants grounded in enterprise knowledge: retrieval
should return only the evidence the person asking is entitled to see. Binding that rule to
the data, letting signed-in channels query with the caller's own identity and giving
anonymous traffic a least-privileged public identity, never one shared privileged account,
keeps the decision in one governed place. Sovereign Shield does not include an assistant,
but its gateway faces the same identity question.

### Evidence

With prerequisites already in place, a complete Azure deployment came up in about 42
minutes and tore down in about 35, for US$10 or less in Azure charges. Those are synthetic
evaluation numbers, not production estimates. The code, white paper and an open
reconstruction challenge are here: https://github.com/botlhale/sovereign-shield

*Independent, educational work on synthetic data and public standards, written in a
personal capacity. It is not the work of the Bank of Canada or any other institution, and
the views are my own.*

**Where would you draw the line between discovery and disclosure?** If you have solved this
differently, in statistics or elsewhere, I would like to compare notes.

#SDMX #DataGovernance #Databricks #StatisticalDisclosureControl #DataArchitecture

---

## Part B: Feed Text When Sharing the Article

```text
Can a contractor, or an AI coding agent, build the controls that protect confidential statistics without ever seeing the data?

I tested that question on Azure Databricks with Sovereign Shield, an independent reference architecture built on synthetic data only.

The pattern in four steps:
1. Contract, not data: builders get the SDMX structure, codelists, validation rules and a persona matrix, never the filings.
2. Policies travel with the table: Unity Catalog row filters and column masks decide per caller, per row and per cell.
3. Prove it offline: more than 240 credential-free tests fail if a control is removed.
4. Hand over and revoke: the institution owns every identity and offboards the builders.

The part I most want challenged is a Discovery Gateway: researchers can learn that a confidential cell exists without learning its value or exactly what it describes.

The article also covers what this does not solve. Access control is not disclosure control, and a published total can still give a restricted cell away.

Where would you draw the line between discovery and disclosure?

Code, white paper and an open reconstruction challenge: https://github.com/botlhale/sovereign-shield

Independent, educational work in a personal capacity; views are my own and no institutional or vendor endorsement is implied.

#SDMX #DataGovernance #Databricks #StatisticalDisclosureControl
```
