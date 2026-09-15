# SovereignShield Publication Plan

**Author:** Botlhale Mosweu, in a personal capacity. **Positioning:** independent architect and SDMx practitioner; Augmenta Systems is the project steward, not an institutional sponsor.

## Technical Post

Use after freezing a tested revision and checking the linked evidence and rights/provenance gates. This is plain text suitable for LinkedIn, not a claim that the revised cloud deployment is already verified.

```text
How can an external data specialist build a governed statistical platform without access to its production records?

Through my participation in the SDMx community, I've become interested in the different architectures that can support the same statistical contracts. SovereignShield is one independent Azure-native example I built using synthetic submissions, Azure Databricks, Unity Catalog, Delta Lake and pysdmx.

The delivery model starts with production-shaped synthetic data and an explicit group-access matrix. A submitter sees its own filings plus public foreign observations. Researchers can discover published series with restricted values withheld, providing a basis for a separate agreement with the originating country. The public sees only publishable observations; administrators can inspect the full audit history.

The difficult questions sit between those layers: can policy updates preserve existing protection, does replay retain one copy of a filing, what happens when an accepted revision contains fewer observations, and does an export preserve precision and lifecycle meaning?

The current local tests exercise those cases. Accepted snapshots and rejected filings remain separate, standard SDMx exports are current/published-only, and audit CSV retains submission identity and failure feedback. The reference profile demonstrates three decimal places. Company-controlled runtime identities make continuity independent of an individual contractor's account.

There are important limits. Row filtering and masking are not complete statistical disclosure control: public totals can reveal a suppressed component. Local tests are not production accreditation, and this revision's live migration and acceptance remain outstanding.

This complements established SDMx tooling. It does not suggest that institutions lack effective controls or have not adopted cloud platforms.

Developed in a personal capacity using synthetic data and public standards. No employer, statistical institution or vendor affiliation or endorsement is implied.

The repository includes a short executive brief, the full whitepaper, reproducible tests and explicit limitations. I welcome technical review, especially on disclosure control, submission semantics and institutional adoption.

https://github.com/botlhale/sovereign-shield

#SDMx #DataArchitecture #Interoperability #DataGovernance
```

## Brief and Video

The accompanying brief is [EXECUTIVE_BRIEF.md](EXECUTIVE_BRIEF.md), a separate eight-section decision document. The [full whitepaper](whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md) is the deeper technical companion. Use a proofread, version-labelled PDF of the brief for a native LinkedIn document, with the repository URL in the post. Keep limitations and independent-work notice visible.

A video is optional, not a launch prerequisite or a guaranteed reach multiplier. A later short walkthrough can show public, researcher, submitter quarantine feedback, and administrator audit views. Use [the persona script](PERSONA_DEMO_SCRIPT.md), label any local/mocked persona demonstration, and never display tokens, real credentials or institutional data. Historical anonymized screenshots are not fresh deployment captures.

LinkedIn supports [document uploads](https://www.linkedin.com/help/linkedin/answer/a518909); published documents cannot simply be replaced, so proof the final artifact first. There is no reliable universal rule that outbound links must be hidden in comments. Prefer a directly usable evidence link. Views, clones and impressions are not qualified consulting leads; measure technical reviews, relevant conversations, referrals and concrete enquiries.

## Workshop Status

The [2026 SDMx Experts Workshop call](https://www.sdmxexperts2026.org/callforabstracts/) states that abstract submission **closed on 7 September 2026**. The event is scheduled for **30 November to 4 December 2026 in Ankara, Turkiye**. The announcement's word "today" referred to 7 September, not the date of this revision. Do not publish it as an open call or imply acceptance.

Only the organizers can confirm late-submission, poster or discussion opportunities. A possible abstract for an organizer-approved opportunity or a future event follows; it has not been submitted.

### Draft Abstract

**Synthetic-First Delivery of a Governed SDMx Platform on Azure**

External specialists can implement statistical platforms more safely when the delivery contract includes realistic synthetic submissions, explicit group-access boundaries and reproducible lifecycle tests. This independent reference study explores that approach using BIS LBS-shaped synthetic data, pysdmx, Azure Databricks, Unity Catalog and Delta Lake.

The implementation separates structural and codelist checks from arithmetic acceptance, retains rejected arrivals without displacing accepted state, and distinguishes current SDMx dissemination from submission-aware audit exports. It tests immutable submission identity, replay, smaller full replacements, three-place decimal preservation and policy-deployment failures. Group-based access supports public dissemination, researcher discovery, own-country submission feedback and privileged audit review. Stable service-principal execution supports continuity after contractor offboarding.

The contribution is an inspectable integration and delivery pattern, not a replacement for existing SDMx registries or reference infrastructure. Local evidence is distinguished from historical cloud demonstrations. Remaining work includes full provisioning constraints, independent rule semantics, live migration acceptance, distributed performance and statistical disclosure control. In particular, query-time masking does not prevent inference from published totals. The study invites discussion of the evidence institutions require before adopting a production-isolated delivery model.

## Attribution and Release Checks

Plain-text technology names describe dependencies; they do not imply sponsorship, certification or a trademark licence. Avoid unapproved logos and organizational endorsements. Naming rules and publication rights are context-dependent; this document is not legal advice.

Consulting clearance reported by the author is acknowledged, but does not by itself certify this exact publication, ownership assignment or third-party redistribution. Keep Botlhale Mosweu's authorship clear, identify company stewardship separately, and retain the existing copyright line until the rights-holder is confirmed. The personal-capacity disclaimer is context, not immunity.

- Freeze the tested revision, evidence commands and limitations.
- Complete the [release and migration gates](RELEASE_EVIDENCE.md) before claiming live readiness.
- Review [third-party provenance](reference_standards/README.md); do not treat public PDFs/workbooks as public domain.
- Keep the historical password issue accurately described: author reports it is no longer used; no current incident is asserted.
- Ensure every screenshot, benchmark and credential/control claim identifies its actual environment.
- Seek technical critique without suggesting shortcomings in an employer or other institution.