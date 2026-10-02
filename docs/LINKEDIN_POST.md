# LinkedIn Publication Plan

**Recommendation:** lead with a native LinkedIn **article** that tells the story in the
author's voice, follow it with the [Executive Brief](EXECUTIVE_BRIEF.md) as a document post,
and publish one technical follow-up a week later. The Executive Brief and
[White Paper](whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md) keep their
shared title, **Bridging Public Dissemination and Protected Data: A Zero-Trust SDMx
Architecture on Azure Databricks**.

**Author:** Botlhale Mosweu, in a personal capacity. **Project steward:** Augmenta Systems
(13668754 Canada Inc.). No employer, statistical institution or vendor sponsorship is implied.

## Gates Before Posting

1. **Employer clearance.** Confirm outside-activity, intellectual-property and
   public-communication rules in writing. Describe prior experience generically, as in the
   draft below; do not name an employer or describe its systems, controls, data or incidents.
   Keep the independent-work notice, and do not speculate about which cloud any named
   international organization uses.
2. **Evidence.** Freeze a reviewed commit and record its test output. Complete the
   [Discovery Gateway acceptance](RELEASE_EVIDENCE.md#discovery-gateway-acceptance) on a
   synthetic workspace, or describe coordinate masking as "implemented and tested offline".
3. **Rights and proofing.** Clear third-party artifacts and screenshots, then proof every
   image and PDF on a desktop and a phone. LinkedIn
   [documents](https://www.linkedin.com/help/linkedin/answer/a518909) accept PDF up to 100 MB
   and 300 pages and cannot be replaced after posting; a correction needs a new post.

## 1. Anchor Article

Use **Write article** from the home page. Cover image: [executive architecture](figures/executive_architecture.png).
Inline images: the [Discovery Gateway capture](../demo/researcher_discovery_view.png) and the
[triple-lock figure](figures/triple_lock.png). Keep the repository link in the body.

```text
Build without seeing: letting contractors and AI agents engineer a central-bank data platform without touching confidential data

My work has long sat where data governance meets international statistics: group-based row-level security for regulatory returns on a commercial cloud platform, and a banking statistics pipeline modernized to produce SDMX 3.0. At SDMX community events, three conversations kept coming back.

Executives want masking they can trust: not "the developer promises not to look", but controls no developer can talk their way around.
Data holders want to work with researchers without handing over the data.
Reporting analysts who file several submissions want a simple answer: which copy does the international organization actually hold?

International organizations often build their SDMX stacks on open source, while many central banks run on a commercial cloud. I wanted to see what the same guarantees look like on Azure Databricks, so I built Sovereign Shield: an independent reference architecture, on synthetic data only.

The contractor dilemma
Statutory confidentiality says contributors' data is used for statistics and released only when no one can be identified. Yet the engineering that enforces it (Unity Catalog policies, Delta Lake history, SDMX serialization, Terraform) is increasingly delivered by integrators, contractors and AI coding agents. Giving builders production access in order to build the controls that protect production is a contradiction.

The pattern: build without seeing
1. Contract, not data. The client approves metadata only: the BIS LBS 1.0 structure, codelists, 21 validation rules and a persona matrix. Builders generate synthetic SDMX filings that exercise every branch.
2. Policies travel with the table. Unity Catalog row filters and column masks decide per caller, per row and per cell. The same SQL runs in staging and production.
3. Prove it offline. More than 240 credential-free tests fail if a control is removed.
4. Hand over and revoke. The client imports a reviewed release, owns every identity and offboards the provider.

Four personas read one governed store: the public sees free values; submitting analysts see their own filings in every state, so they can reconcile what they sent with what the receiver holds; administrators see the full audit trail; and researchers get something new.

The idea I most want feedback on: a Discovery Gateway
A researcher should be able to discover that confidential data exists, so they can approach the submitting central bank, without learning the value or even exactly what it describes. For restricted cells the platform withholds the value and masks the counterparty: Q.S.C.A.USD.D.5J.A.US.A.5J becomes Q.S.C.A.USD.D.5J.A.US.xx.xx. Restricted rows never appear in a download, so a researcher's export is identical to the public one.

Two lessons surprised me.
Masking a value is not enough if you leave its fingerprints. A row hash built from the full key can be brute-forced back to hidden coordinates in a few thousand guesses, and a payload hash confirms a guessed value. Both are now masked by the same rule.
Masks must resolve before filters, or a researcher can filter by counterparty and watch which restricted row appears. Unity Catalog applies masks first, and the tests hold the local mirror to the same rule.

What it does not solve
Access control is not disclosure control. In the synthetic data, a published total of 1,000 minus public components of 400 and 500 still reveals a restricted cell of 100, masked coordinates or not. That needs complementary suppression decided by the data authority. Researchers who genuinely need restricted cells belong in a secure enclave: approved projects, no raw export, reviewed outputs. That part is a concept, not code.

Evidence
A complete Azure deployment came up in about 75 minutes and tore down in 30, for under US$10 in Azure charges. Those are synthetic evaluation numbers, not production estimates. The code, white paper and an open reconstruction challenge are here: https://github.com/botlhale/sovereign-shield

Independent work on synthetic data and public standards; no employer, institutional or vendor endorsement.

Where would you draw the line between discovery and disclosure?

#SDMX #DataGovernance #Databricks #StatisticalDisclosureControl #DataArchitecture
```

## 2. Executive Brief Post

Two or three days later, upload the reviewed brief PDF through **Start a post > Add a
document**, titled "Sovereign Shield: Executive Brief".

```text
Can an external team build the controls for confidential statistics without ever seeing the data?

The Executive Brief behind last week's article covers the decision an architecture board faces: four personas over one governed store, how an analyst reconciles the latest filing with the accepted publication, and what still needs a disclosure decision.

Article, white paper and code: https://github.com/botlhale/sovereign-shield
Independent work on synthetic data; no institutional or vendor endorsement.

#SDMX #DataArchitecture #DataGovernance
```

## 3. Technical Follow-Up

About a week after the article, post one focused finding with the triple-lock figure:
"Masking a value but leaving its hash." Show the RECORD_ID and version_hash side channel,
the fix, and the test that fails when the lineage mask is removed. Invite synthetic
reconstruction attempts through the [security challenge](../SECURITY.md#statistical-reconstruction-challenge);
never invite tests against a live deployment.

## 4. Feature and Maintain

Add the article, the brief post and the tagged GitHub Release to **Featured**
(Me > View profile > Add profile section > Recommended > Add featured). Answer technical
questions with evidence and record actionable findings in the repository. Measure
substantive reviews, saves, profile visits from practitioners and qualified conversations,
not impressions or clone counts. The [persona demo script](PERSONA_DEMO_SCRIPT.md) supports
an optional short video; archival and release steps are in
[Publication Venues and GitHub Release](PUBLICATION_AND_RELEASE.md).
