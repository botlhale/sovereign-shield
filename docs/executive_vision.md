# Executive Vision — Image Prompt

**Audience:** Senior Leadership Team, board, non-technical sponsors
**Use:** one slide, 5-minute narrative
**Companion:** [`technical_vision.md`](technical_vision.md) for architects and advisors

![Sovereignty as a Platform Guarantee — three abstract reporting jurisdictions labelled AA, BB and CC submit standardised documents along a pathway; an automated rule check deflects one into a "held for correction" tray while the rest continue into a governed vault wrapped in three rings labelled "who you are", "what you may see" and "what is published"; four audiences draw from that single source through beams of increasing width.](sovereign-shield_executive.jpg)

*Rendered output. Note what is absent: no vendor logo, no national flag, no
identifiable institution — and the non-affiliation caption is part of the image
rather than the slide around it, so it survives being screenshotted.*

---

## Why this prompt is worded the way it is

The earlier `slt_image_prompt.md` instructed the model to render **actual vendor
logos** ("the Microsoft Azure Key Vault icon", "the Microsoft Entra ID icon") and
to draw **national central-bank buildings with flag pennants**. That directly
contradicts the policy stated in the repository README — *"BIS and SDMx are
referenced as typeset text throughout, never as reproduced logos"* — and creates
three avoidable exposures:

| Risk | Why it matters | How this prompt avoids it |
| --- | --- | --- |
| **Trademark use** | Vendor logos are trademarks. Reproducing them in a deck that promotes your own work can imply partnership or endorsement | Vendors named as **typeset text only**, in a neutral "built on" line |
| **Implied institutional affiliation** | Flags and neoclassical bank facades read as *"this is a real central bank system"* | Abstract, non-national jurisdiction markers; no flags, no identifiable buildings |
| **Implied real data** | An audience assumes a data platform diagram shows real data | A mandatory on-image caption stating synthetic data and no affiliation |
| **Generated-logo distortion** | Image models render logos inaccurately, which is worse than omitting them | Nothing logo-shaped is requested at all |

> Generative image tools also frequently refuse or mangle trademark reproduction.
> Removing logos improves output quality as well as your legal position.

**This is not legal advice.** If the deck goes outside your organisation, have
whoever normally reviews external material look at it.

---

## The prompt

Paste whole into Gemini, Microsoft 365 Copilot, DALL·E or Midjourney. Self-contained,
one-shot, no compositing.

```text
Create a polished 16:9 enterprise keynote graphic explaining a data governance
platform for INTERNATIONAL STATISTICAL REPORTING — the submission of confidential
national banking statistics to an international standards body.

STYLE: Premium corporate, clean and confident, suitable for a board presentation.
Light background: soft white on the left blending to pale ice-blue on the right.
Subtle reflective floor, gentle depth. Flat vector illustration with soft
shadows. No photorealism. Muted institutional palette: deep navy, slate grey,
teal accent, warm amber for the one warning element.

CRITICAL CONSTRAINTS — follow exactly:
- Do NOT draw any company logo, brand mark, product icon or trademark.
- Do NOT draw national flags, country outlines, maps, or recognisable
  government or central-bank buildings.
- Do NOT invent institution names. The only text is what is specified below.
- Represent organisations as neutral abstract shapes only.

COMPOSITION: a single left-to-right narrative along a softly glowing horizontal
pathway, in four zones.

ZONE 1 — FAR LEFT, "REPORTING JURISDICTIONS". Three identical simple hexagonal
tiles stacked vertically, each a different muted colour (slate blue, muted teal,
warm grey), each bearing only a two-letter abstract placeholder in clean sans
type: "AA", "BB", "CC". No flags. From each tile a crisp white document glyph
marked with angle brackets < > drifts rightward and merges onto the pathway.
Label beneath the group: "REPORTING JURISDICTIONS". Label on the document
stream: "STANDARDISED SUBMISSIONS".

ZONE 2 — LEFT-CENTRE, "AUTOMATED VALIDATION". A tall translucent glass gate
across the pathway. Most documents pass through and continue. ONE document is
deflected downward into a small amber-outlined tray beneath the pathway, marked
with a clean pause symbol. Label above the gate: "AUTOMATED RULE CHECK". Label
on the amber tray: "HELD FOR CORRECTION". A thin caption beneath: "One
jurisdiction's error never blocks another's".

ZONE 3 — CENTRE, "THE GOVERNED VAULT". The visual anchor: a large softly glowing
translucent cylinder standing on the pathway, deep navy with an inner teal light.
Wrapped around it, three concentric rings, each a different tone, each labelled
in small clean type on the ring itself:
  inner ring  — "WHO YOU ARE"
  middle ring — "WHAT YOU MAY SEE"
  outer ring  — "WHAT IS PUBLISHED"
Label beneath the cylinder: "POLICY ENFORCED AT THE DATA, NOT IN THE APPLICATION".

ZONE 4 — RIGHT, "FOUR AUDIENCES, ONE SOURCE". Four simple abstract human
silhouettes in a row, each standing on a small white pedestal, each connected
back to the cylinder by a distinct coloured beam. Beside each figure a compact
card with a title and one short line:

  Figure 1, grey beam, card: "PUBLIC" / "Published figures only"
  Figure 2, indigo beam, card: "RESEARCHER" / "All published data, sensitive
    values hidden"
  Figure 3, teal beam, card: "NATIONAL ANALYST" / "Own jurisdiction in full"
  Figure 4, deep red beam, card: "AUDITOR" / "Complete view, fully accountable"

Show the beams as visibly different widths — narrowest to the PUBLIC figure,
widest to the AUDITOR figure — so the graduation of access is obvious at a glance.

TITLE, top-left, large and confident:
  "Sovereignty as a Platform Guarantee"
SUBTITLE, directly beneath, smaller:
  "Confidential statistical exchange, governed at the data layer"

FOOTER, bottom edge, small but clearly legible, in neutral grey:
  "Independent reference architecture · Illustrative synthetic data · Not
  affiliated with or endorsed by any central bank or international organisation"

Balanced composition, generous white space, no clutter. Every label must be
crisp and correctly spelled.
```

---

## Read-aloud narrative — 5 minutes

> **Slide up. Pause. Let them read the title.**

Every quarter, national authorities send confidential banking statistics to an
international body. Three obligations apply at once, and they pull against each
other.

**One — sovereignty.** A country's detailed figures are its own. They must not be
visible to another country, even one sitting inside the same shared system.

**Two — confidentiality.** Inside a country's own submission, some figures could
identify a single institution. Those must be withheld from researchers while the
surrounding structure stays intact.

**Three — integrity.** Nothing internally inconsistent may be published. Not the
inconsistent part — *none of it*, because the totals that reconcile depend on the
components that did not.

*(Gesture to Zone 2.)*

Today those obligations are upheld by careful process and specialised software,
and they are upheld well. The question this work asks is different: **what if
they were properties of the platform itself, rather than rules the application
is trusted to follow?**

*(Gesture to Zone 3 — the cylinder and its rings.)*

That is what this is. The rules live *with the data*, not in the software that
reads it. Which means they apply the same way whether someone arrives through a
report, a spreadsheet, a public web page, or a direct database connection.

There is no code path that can forget to apply them, because they are not in the
code path at all.

*(Gesture to Zone 4 — the four figures and the widening beams.)*

Same data. Four audiences. Four different answers — and the difference is
produced by the platform, not by four different applications we have to keep in
step with each other.

**Three things worth taking away.**

**Correct by construction.** A new report, a new tool, a new analyst — the rules
already apply. Nobody has to remember.

**Off-boarding is instant.** Remove someone from a group and they see nothing.
Not "less" — nothing. The same mechanism that keeps two countries apart is the
one that removes a departing contractor. There is no separate switch to forget.

**It was built without the real data.** Everything you are looking at was
developed and demonstrated against generated figures. The specialist who built it
never held a real submission. That is not a limitation of the demonstration — it
is the delivery model.

> **Anticipated question: "Is this in production?"**
> No. It is a working reference architecture on synthetic data, built to test
> whether the approach holds. What it demonstrates is that the controls can be
> expressed as platform constraints — and that the same constraints activate on
> real data at first run, with no separate hardening phase.

---

## Adaptation notes

* **Board or regulator audience** — enlarge the footer disclaimer and repeat it
  verbally in the first fifteen seconds.
* **Naming the vendors** — if the deck must show the technology stack, add one
  neutral typeset line beneath the footer: *"Built on Azure Databricks and
  Microsoft Entra ID."* Typeset text is nominative use; a rendered logo is not.
* **If asked for a real jurisdiction** — substitute real ISO codes in Zone 1
  only after confirming with your reviewer that no institutional affiliation is
  implied. The abstract placeholders exist to make that a conscious decision
  rather than a default.
