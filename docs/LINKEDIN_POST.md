# LinkedIn Publication Plan

**Purpose:** share what this project teaches about governed statistical exchange and
AI-assisted delivery, and make the work visible to practitioners who may want to review,
extend or collaborate on it. Each post teaches one transferable lesson and links to the
evidence; none offers services, rates or availability. Collaboration and partnership
proposals are a welcome outcome, not the target.

**Recommendation:** lead with a native LinkedIn **article** that tells the story in the
author's voice, follow it with the [Executive Brief](EXECUTIVE_BRIEF.md) as a document post,
and publish one technical follow-up a week later. The Executive Brief and
[White Paper](whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md) keep their
shared title, **Bridging Public Dissemination and Protected Data: A Least-Privilege SDMx
Architecture on Azure Databricks**.

**Author:** Botlhale Mosweu, in a personal capacity. This is not the work of the Bank of
Canada or any other institution, and no employer, statistical institution or vendor
sponsorship is implied.

## Gates Before Posting

1. **Independence and attribution.** State that the work is personal, educational, based on
   synthetic data and not the work of any employer or institution, and add "views are my
   own". Describe prior work only at the level already public, and never describe internal
   systems, controls, data or incidents. Keep other organizations' technology choices out of
   public material, even when known from professional contact.
2. **Evidence.** Freeze a reviewed commit and record its test output. Complete the
   [Discovery Gateway acceptance](RELEASE_EVIDENCE.md#discovery-gateway-acceptance) on a
   synthetic workspace, or describe coordinate masking as "implemented and tested offline".
3. **Rights and proofing.** Clear third-party artifacts and screenshots, then proof every
   image and PDF on a desktop and a phone. LinkedIn
   [documents](https://www.linkedin.com/help/linkedin/answer/a518909) accept PDF up to 100 MB
   and 300 pages and cannot be replaced after posting; a correction needs a new post.

## Teach, Don't Sell

- Lead with the problem and the lesson; the repository is the evidence, not an offer.
- Show limits and failures as prominently as results; candour is what makes the work reusable.
- End with a question or an invitation to challenge, port or co-author, never a call to hire.
- Credit the standards, tools and communities the work builds on, such as SDMx, the BIS and pysdmx.

## 1. Anchor Article

Use **Write article** from the home page. Cover image: [executive architecture](figures/executive_architecture.png).
Inline images: the [Discovery Gateway capture](../demo/researcher_discovery_view.png) and the
[triple-lock figure](figures/triple_lock.png). Keep the repository link in the body.

```text
Build without seeing: how contractors and AI agents can engineer a statistical data platform without touching confidential data

My work has long sat where data governance meets international statistics: group-based row-level security for regulatory returns on a commercial cloud platform, and a banking statistics pipeline modernized to produce SDMX 3.0. At SDMX community events, three conversations kept coming back.

Executives want masking they can trust: not "the developer promises not to look", but controls no developer can talk their way around.
Data holders want to work with researchers without handing over the data.
Reporting analysts who file several submissions want a simple answer: which copy does the international organization actually hold?

International organizations often build their SDMX stacks on open source, while many central banks run on a commercial cloud. I wanted to see what the same guarantees look like on Azure Databricks, so I built Sovereign Shield, an independent reference architecture on synthetic data only, and published the code, evidence and limits so others can study, reuse and challenge it.

The contractor dilemma
Statutory confidentiality says contributors' data is used for statistics and released only when no one can be identified. Yet the engineering that enforces it (Unity Catalog policies, Delta Lake history, SDMX serialization, Terraform) is increasingly delivered by integrators, contractors and AI coding agents. Giving builders production access in order to build the controls that protect production is a contradiction.

The pattern: build without seeing
1. Contract, not data. The data owner approves metadata only: the BIS LBS 1.0 structure, codelists, 21 validation rules and a persona matrix. Builders generate synthetic SDMX filings that exercise every branch.
2. Policies travel with the table. Unity Catalog row filters and column masks decide per caller, per row and per cell. The same SQL runs in staging and production.
3. Prove it offline. More than 240 credential-free tests fail if a control is removed.
4. Hand over and revoke. The institution imports a reviewed release, owns every identity and offboards the builders.

Four personas read one governed store: the public sees free values; submitting analysts see their own filings in every state, so they can reconcile what they sent with what the receiver holds; administrators see the full audit trail; and researchers get something new.

The idea I most want feedback on: a Discovery Gateway
A researcher should be able to discover that confidential data exists, so they can approach the submitting central bank, without learning the value or even exactly what it describes. For restricted cells the platform withholds the value and masks the counterparty: Q.S.C.A.USD.D.5J.A.US.A.5J becomes Q.S.C.A.USD.D.5J.A.US.xx.xx. Masked rows never appear in a download, so a researcher's export is identical to the public one.

Two lessons surprised me.
Masking a value is not enough if you leave its fingerprints. A row hash built from the full key can be brute-forced back to hidden coordinates in a few thousand guesses, and a payload hash confirms a guessed value. Both are now masked by the same rule.
Masks must resolve before filters, or a researcher can filter by counterparty and watch which restricted row appears. Unity Catalog applies masks first, and the tests hold the local mirror to the same rule.

What it does not solve
Access control is not disclosure control. In the synthetic data, a published total of 1,000 minus public components of 400 and 500 still reveals a restricted cell of 100, masked coordinates or not. That needs complementary suppression decided by the data authority. Researchers who genuinely need restricted cells belong in a secure enclave: approved projects, no raw export, reviewed outputs. That part is a concept, not code.

Beyond statistics
The same question now faces AI assistants grounded in enterprise knowledge: retrieval should return only the evidence the person asking is entitled to see. Binding that rule to the data, letting signed-in channels query with the caller's own identity and giving anonymous traffic a least-privileged public identity, never one shared privileged account, keeps the decision in one governed place. Sovereign Shield does not include an assistant, but its gateway faces the same identity question.

Evidence
A complete Azure deployment came up in about 75 minutes and tore down in 30, for under US$10 in Azure charges. Those are synthetic evaluation numbers, not production estimates. The code, white paper and an open reconstruction challenge are here: https://github.com/botlhale/sovereign-shield

Independent, educational work on synthetic data and public standards, written in a personal capacity. It is not the work of the Bank of Canada or any other institution, and the views are my own.

Where would you draw the line between discovery and disclosure? If you have solved this differently, in statistics or elsewhere, I would like to compare notes.

#SDMX #DataGovernance #Databricks #StatisticalDisclosureControl #DataArchitecture
```

## 2. Executive Brief Post

Two or three days later, upload the reviewed brief PDF through **Start a post > Add a
document**, titled "Sovereign Shield: Executive Brief".

```text
Can an external team build the controls for confidential statistics without ever seeing the data?

The eight-page Executive Brief behind last week's article summarizes the pattern for architecture boards: four personas over one governed store, how an analyst reconciles the latest filing with the accepted publication, and what still needs a disclosure decision. It closes with the questions worth asking before any pilot.

Article, white paper and code: https://github.com/botlhale/sovereign-shield
Independent, educational work on synthetic data; views are my own and no institutional or vendor endorsement is implied.

#SDMX #DataArchitecture #DataGovernance
```

## 3. Technical Follow-Up

About a week after the article, post one focused finding with the triple-lock figure:
"Masking a value but leaving its hash." Show the RECORD_ID and version_hash side channel,
the fix, and the test that fails when the lineage mask is removed, then generalize the
lesson to any masked dataset. Invite synthetic reconstruction attempts through the
[security challenge](../SECURITY.md#statistical-reconstruction-challenge); never invite
tests against a live deployment.

## 4. Optional Bridge Post

Enterprise AI discussions increasingly treat retrieval, entitlement and evaluation as shared
services behind many assistants. A short post can reach that audience without overstating
the work: "Entitlement-aware retrieval: what a statistical Discovery Gateway teaches
enterprise knowledge systems." Cover entitlements bound to the data rather than to each
assistant, signed-in channels that query with the caller's identity while anonymous traffic
uses a least-privileged public identity
([perimeter identity](whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md#the-perimeter-identity-problem)),
and confirming that evidence exists without disclosing it. Close with the limit that
entitlement is not disclosure control. Say plainly that the repository contains no AI
assistant, and link and credit any article the post responds to.

## 5. Feature, Engage and Measure

Add the article, the brief post and the tagged GitHub Release to **Featured**
(Me > View profile > Add profile section > Recommended > Add featured). Answer technical
questions with evidence and record actionable findings in the repository. Measure learning
and reach among practitioners: substantive comments and reviews, saves, reconstruction
attempts, issues and pull requests, ports to other platforms, and invitations to speak,
co-author or collaborate, not impressions or clone counts. The
[persona demo script](PERSONA_DEMO_SCRIPT.md) supports an optional short video; archival
and release steps are in [Publication Venues and GitHub Release](PUBLICATION_AND_RELEASE.md).
