# SovereignShield — Persona Demo Narrative

**Audience:** statistical leaders, data architects, central-bank analysts, research partners  
**Format:** 3–5 minute LinkedIn video  
**Companions:** [Executive vision](executive_vision.md) · [Technical vision](technical_vision.md) · [Whitepaper](whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md)

---

## Positioning

The demo and the architecture pattern should remain separate but connected.

- **The demo explains institutional value through user journeys.** It shows what a public visitor, researcher, reporting authority and administrator can do.
- **The architecture explains why those views can be trusted.** Unity Catalog row filters and column masks enforce the differences at query time.
- **The whitepaper provides the durable argument.** It records the design, standards, controls and operating model beyond what fits in a short video.

For LinkedIn, lead with the demo. Use one brief architecture transition near the end, then link to the whitepaper and repository for evidence. The video earns attention; the architecture earns confidence; the whitepaper supports serious evaluation.

---

## Product motivation

### Discoverability without disclosure

Public statistical portals are designed to publish data that is already free to disseminate. That is necessary, but it leaves a gap for legitimate research collaboration: a researcher cannot request access to a protected series they do not know exists.

SovereignShield gives registered researchers a controlled view of the published statistical structure. Restricted observations remain present, but their values are masked. A researcher can identify that a relevant series exists, understand its dimensions and reporting jurisdiction, and approach the appropriate authority with a specific research proposal. Disclosure still requires a separate agreement and approval process; discoverability does not become access.

This creates a clearer path from:

```text
unknown data → visible protected series → informed request → institutional agreement
```

### Submission assurance and feedback

A reporting authority may submit several versions for the same period. It should be able to answer:

- Which version does the international organisation currently publish?
- Was a revision quarantined?
- Did the prior accepted submission remain active?
- Which validation rules rejected the new filing?

The national analyst view provides this assurance. Analysts see their own jurisdiction in full, including confidential values and their own quarantined revisions, while foreign jurisdictions remain at the public entitlement. The international organisation retains the complete audit history without exposing one country's restricted data to another.

This creates a practical validation feedback loop:

```text
submit → validate → publish or quarantine → inspect outcome → reconcile rule interpretation → improve the next filing
```

SovereignShield currently demonstrates visibility of published and quarantined versions. `FAILED_RULE_ID` is retained in the governed history and API result model; presenting rule-level diagnostics directly in the portal would be a logical product extension for operational users.

---

## Demo script

### 0:00–0:25 — Open with the problem

**Screen:** Public view, all filters reset.

**Narration:**

> Statistical portals are very good at showing what can be published. The harder question is how one platform can also serve researchers, reporting authorities and auditors without copying data into separate systems or trusting each application to apply the rules correctly.

> SovereignShield is a working reference architecture for that question. The data is synthetic, the structure is real SDMx 3.0, and every persona queries the same governed table while Unity Catalog produces different rows and values for each caller.

**On screen:** Point to the `Public (Free to Publish Only)` badge and the 13-observation result.

**Significance:** Establish that anonymous access is useful and intentionally limited, not a failed authentication state.

---

### 0:25–1:05 — Public dissemination

**Screen:** Public view. Open Reporting Country and Currency filters briefly; select and clear one option to show live filtering.

**Narration:**

> An anonymous visitor sees only current observations that passed validation and are explicitly free to publish. Here that is 13 observations. The filter menus are built from the rows this identity is allowed to discover, and every selection updates the result immediately.

> The gateway chooses the identity used for the query. It does not decide which rows are returned. Unity Catalog applies that decision inside the data platform.

**Significance:** Public access is an explicit, auditable entitlement through the public proxy identity. It is not a permissive default.

---

### 1:05–1:50 — Research discoverability

**Screen:** Researcher view showing 22 published observations and 9 masked values.

**Narration:**

> A registered researcher sees a different answer from the same table. All 22 published observations remain visible, preserving the statistical structure, but nine protected values are rendered as restricted.

> This matters beyond masking. It lets a researcher discover that a series exists, identify its reporting jurisdiction and dimensions, and form a precise request for collaboration. They can approach the relevant central bank and explain why a research agreement would benefit from that protected series. The platform points them in the right direction without disclosing the value.

> Registration is not approval to use confidential data. It is a controlled discovery tier that can support a separate legal and institutional process.

**On screen:** Point to the researcher badge, the withheld-value count and two `restricted` observations.

**Significance:** Demonstrates discoverability without disclosure and preserves dimensional density for research planning.

---

### 1:50–2:45 — Reporting-authority assurance

**Screen:** Bank of Canada view, then Federal Reserve view.

**Narration:**

> A reporting authority needs a different form of confidence. The Bank of Canada analyst sees Canadian restricted values in full, but foreign protected observations remain outside its entitlement. The Federal Reserve analyst receives the mirror image.

> This is useful when several filings exist for the same period. The analyst can verify what the international organisation currently holds and what remains published. Sovereignty restricts depth, not access to data that is already public.

**Screen:** In the Bank of Canada view, turn on `Include quarantine`.

> The analyst can also include its own quarantined revision. A rejected filing is retained for diagnosis, but it does not replace the last accepted version. That means a failed revision degrades to stale data, never missing data.

> This supports a better conversation between the reporting authority and the international organisation: did our local checks differ, did we interpret a rule differently, or does one side need to tighten its validation? The history makes that discussion specific and evidence-based.

**Significance:** Demonstrates national isolation, own-country confidentiality, revision transparency and prior-state preservation.

---

### 2:45–3:25 — International organisation oversight

**Screen:** Administrator view with quarantine off, then on.

**Narration:**

> The platform administrator sees all 22 published observations unmasked across all jurisdictions. When quarantine is included, the view expands to 44 rows: the accepted baseline and the audit-only revisions.

> Published and quarantined versions remain visibly distinct. The administrator can investigate quality outcomes without allowing a failed revision into dissemination.

**On screen:** Toggle quarantine and point to paired `PUBLISHED` and `QUARANTINE` badges for the same period.

**Significance:** Demonstrates cross-jurisdiction oversight, complete lineage and separation of publication from audit.

---

### 3:25–4:05 — Show the architecture pattern

**Screen:** Use the technical architecture diagram or briefly show the repository diagram.

**Narration:**

> These are not five separately coded views. The gateway carries the caller's identity to the SQL warehouse, and Unity Catalog evaluates row-level security and dynamic data masking against that identity at query time.

> The same table therefore produces five outcomes: public, researcher, Canadian submitter, US submitter and administrator. A principal in none of the recognised groups receives zero rows.

> Quality is enforced separately. SDMx submissions are checked against the published BIS consistency workbook. A failed country-period is quarantined atomically, and Delta Lake keeps the complete SCD Type 2 history.

**Significance:** Connect the visible product behavior to platform-enforced controls without turning the video into an implementation walkthrough.

---

### 4:05–4:30 — Close with the claim and boundary

**Screen:** Return to the public view or a four-persona montage.

**Narration:**

> The product idea is straightforward: make public statistics genuinely public, make protected series discoverable without disclosing them, give reporting authorities confidence in what was received, and give the international organisation one governed audit trail.

> This is an independent reference architecture using synthetic data. It is not affiliated with or endorsed by the BIS, any central bank or any vendor named. The whitepaper, architecture diagrams, tests and deployment code are available in the repository.

> The question I would put to statistical organisations is: could a controlled discovery and submission-feedback layer improve how researchers and reporting authorities work with the data you already govern?

---

## Recording plan

| Shot | Persona | State to capture | Product claim |
| --- | --- | --- | --- |
| 1 | Public | 13 published/free observations | Open dissemination is explicit and fail-closed |
| 2 | Researcher | 22 published rows, 9 values restricted | Series are discoverable without disclosure |
| 3 | Bank of Canada | 14 published rows; own restricted values visible | A submitter sees its jurisdiction in full |
| 4 | Federal Reserve | 17 published rows; own restricted values visible | Sovereignty is symmetric between submitters |
| 5 | Bank of Canada | Include quarantine enabled | A submitter can inspect its rejected revision |
| 6 | Administrator | 22 published rows, then 44 with quarantine | Full oversight and complete audit history |
| 7 | Architecture | Triple-lock and identity flow | The platform, not the page, enforces entitlement |

Use the compact filters during transitions rather than narrating every dimension. One multi-select example is enough: choose two reporting countries to demonstrate that the portal is an analytical tool, not a sequence of static screenshots.

---

## Claims and boundaries

### Demonstrated now

- Anonymous public dissemination of `PUBLISHED/F` observations.
- Registered researcher access to all published series with protected values masked.
- Sovereign submitter access to own restricted observations and own quarantine history.
- Administrator access across jurisdictions and lifecycle states.
- Immediate multi-select filtering and persona-scoped filter values.
- SDMx-ML, SDMx-JSON, SDMx-CSV and tidy CSV exports under the caller's entitlement.
- Unity Catalog enforcement, atomic quarantine and SCD2 prior-state preservation.

### Product extensions, not current claims

- Researcher registration, accreditation and agreement workflow.
- In-portal contact routing to the reporting authority that owns a restricted series.
- Access-request review, approval, expiry and purpose limitation.
- Portal presentation of `FAILED_RULE_ID`, validation evidence and bilateral case management.
- Notifications when a submission is published, quarantined or superseded.

Keeping this boundary explicit strengthens the demo: it shows a complete control pattern and a credible product direction without presenting workflow ideas as implemented features.

---

## Demo or whitepaper?

Use both, for different jobs.

- **Demo video:** best for reach, product comprehension and stakeholder conversation. It makes the persona differences tangible in under five minutes.
- **Whitepaper:** best for architectural review, assurance, procurement and technical challenge. It explains why the behavior is trustworthy and where the design stops.
- **Recommended sequence:** publish the short demo with a concise motivation post; link the whitepaper and repository in the first comment; follow later with a focused architecture post.

The demo should stand on the institutional problem. The architecture should substantiate the answer, not lead the story.
