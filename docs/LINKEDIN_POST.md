# SovereignShield — Public Write-Up

**Mix:** ~70% senior leadership, ~30% architects and advisors.
**Rule for every version below:** no claim that the repository cannot back up.

Three lengths. Pick one, do not stack them.

* **[Long](#long-version)** — the flagship post. Leads on the business problem,
  earns technical credibility in the middle, closes on the limits.
* **[Short](#short-version)** — for a busy feed, or as a comment under someone
  else's post about data sovereignty.
* **[Comment reply](#comment-reply-for-the-inevitable-question)** — the answer to
  "is this production?", which will be the first question.

Attach [`sovereign-shield_executive.jpg`](sovereign-shield_executive.jpg) to the
long and short versions. Rationale in [Image selection](#image-selection).

---

## Long version

> Every quarter, national authorities send confidential banking statistics to an
> international body. Three obligations apply at once — and they pull against
> each other.
>
> **Sovereignty.** A country's detailed figures are its own. They must not be
> visible to another country, even inside a shared system.
>
> **Confidentiality.** Within a country's own submission, some figures could
> identify a single institution. Those must be withheld from researchers while
> the surrounding structure stays intact.
>
> **Integrity.** Nothing internally inconsistent may be published. Not the
> inconsistent part — *none of it*. The totals that reconcile depend on the
> components that did not.
>
> Institutions uphold all three today, rigorously, using mature specialised
> software and decades of operational protocol. I am not proposing a replacement.
>
> I spent a few weeks on an adjacent question:
>
> **What if those obligations were properties of the platform itself, rather
> than rules the application is trusted to follow?**
>
> ---
>
> **What that changes**
>
> The rules live *with the data*, not in the software that reads it. So they
> apply identically through a dashboard, a notebook, a spreadsheet, a public web
> page, or a direct database connection.
>
> There is no code path that can forget to apply them — because they are not in
> the code path at all.
>
> Four audiences query the same table and get four different answers:
>
> → **Public** — published, free-to-publish figures only
> → **Researcher** — everything published; sensitive values arrive blank
> → **National analyst** — their own jurisdiction in full, other countries' public data only
> → **Auditor** — the complete picture, including the audit trail
>
> A fifth case matters more than the four: **someone in none of those groups sees
> zero rows.** Not an error. Nothing.
>
> Which means off-boarding a contractor and enforcing sovereignty between two
> nations are *the same mechanism*. There is no separate revocation feature to
> forget, to let rot, or to test less rigorously than the primary one.
>
> ---
>
> **The part I did not expect to be the point**
>
> Specialist platform work needs people who have done it before. Those people are,
> almost by definition, outside your organisation. The data is confidential.
>
> The usual answer is procedural: NDAs, supervised environments, quarterly access
> reviews. It works. But it scales with headcount, decays between reviews, and
> leaves residue — accounts and memberships whose removal has to be *verified*
> rather than *guaranteed*.
>
> So the whole thing was built without the data.
>
> Not "with access controls". Without. The organisation publishes a **specification**
> — structure, code lists, the rulebook, the access matrix — and the builder works
> against generated figures. Every test runs on a laptop with no cloud credentials.
> Deployment happens through a federated identity that only a reviewed, merged
> commit can assume.
>
> A leaked copy of the repository is not a data incident. It contains no
> credential and no observation.
>
> ---
>
> **For the architects reading this**
>
> Entitlement is a row filter and a column mask attached to the table in Unity
> Catalog, resolved per caller, per row, at query time. The API gateway in front
> of it **chooses an identity — it never chooses rows.** Compromise it entirely
> and the metastore still refuses.
>
> Three things I would have got wrong without building it:
>
> **1.** The column mask needs the *series key*, not just the confidentiality
> flag. Mask on group membership alone and any national analyst can read every
> other country's restricted figures. I shipped that bug, then caught it — but
> only because the test data covers more than one jurisdiction. A single-country
> fixture cannot detect it.
>
> **2.** My test for that bug was initially **vacuous**. The row filter already
> removed those rows, so the assertion passed against a completely broken mask. I
> only found out by deliberately reintroducing the bug to see if the suite went
> red. It didn't. A test you have never watched fail is a test you have not
> written.
>
> **3.** A rejected submission must degrade to **stale data, never missing data**.
> The previously published figure stays live; the rejection is recorded for audit
> and diagnosis. Getting this wrong doesn't throw an error — it quietly deletes a
> published series.
>
> Infrastructure is Terraform; tables and policy functions are Databricks Asset
> Bundles. Strictly one writer per object — the filters are re-applied on every
> pipeline run, so if Terraform also owned them the two would fight forever.
>
> ---
>
> **What this is not**
>
> It is a reference architecture on **100% synthetic data**. Independent work,
> not affiliated with or endorsed by any central bank or international
> organisation. The statistical standard and the validation rulebook are public
> artefacts; every number flowing through them is generated.
>
> It demonstrates that the control model is correct. It says nothing about
> performance at real volume — that needs a production dry-run I have not done.
>
> Repository in the comments. I would genuinely like to be told where this breaks.

---

## Short version

> Confidential national statistics, shared with an international body. Three
> obligations that pull against each other: **sovereignty**, **confidentiality**,
> **integrity**.
>
> I spent a few weeks asking what happens when you stop enforcing those in
> application code and make them properties of the data platform itself.
>
> Four audiences query the same table and get four different answers. A fifth
> case matters more: someone in no group sees **zero rows** — not an error,
> nothing.
>
> Which means off-boarding a contractor and enforcing sovereignty between two
> nations run through the *same mechanism*. No separate revocation feature to
> forget.
>
> The part I didn't expect to be the point: it was built entirely **without the
> data**. Specification in, working platform out, every test running on a laptop
> with no cloud credentials. A leaked copy of the repo isn't a data incident —
> there's no credential and no observation in it.
>
> Reference architecture, synthetic data, independent work. Repository below —
> tell me where it breaks.

---

## Comment reply, for the inevitable question

Someone will ask whether it's in production. Answer plainly and immediately:

> No — and I'd be suspicious of anyone claiming otherwise on a first pass at
> this. It's a working reference architecture running the genuine published
> validation rulebook and real standard message formats against generated
> submissions.
>
> What it demonstrates is that the controls can be expressed as platform
> constraints rather than application logic. Because they're attached to
> catalogue objects, they activate on real data at first run — there's no
> "productionisation" phase where the security model gets re-implemented, and
> therefore no phase where it can be re-implemented incorrectly.
>
> What it does *not* demonstrate is behaviour at real volume. That needs a
> production dry-run.

---

## Image selection

**Attach the executive image** (`sovereign-shield_executive.jpg`) to both the
long and short posts.

It reads at thumbnail size, which is the only size most people will see. The
narrative runs left to right, the four audiences are legible without zooming,
and the widening beams communicate graduated access before anyone reads a word.

**Do not lead with the technical diagram.** It is dense by design — excellent
when someone has already asked a question, unreadable in a feed. Hold it back for
a reply, or for the second post in a series.

**Both images carry their disclaimer inside the frame**, not in the caption. This
is deliberate: an image that gets screenshotted, reshared or embedded elsewhere
takes its own context with it. LinkedIn captions do not survive a screenshot.

Neither image contains a vendor logo, a national flag, or an identifiable
institution — which is a legal position, and also a practical one, since image
models render trademarks badly.

---

## Before posting

- [ ] Repository is public, and the README disclaimer is the first thing visible
- [ ] Every number and claim in the post traces to something in the repository
- [ ] The synthetic-data statement appears in the post itself, not only the image
- [ ] No client, employer or institution is named or implied
- [ ] Post the repository link as a **comment**, not in the body — LinkedIn
      suppresses reach on posts with outbound links
- [ ] Be ready for "is this production?" within the first hour

**Tone check.** The credibility of this write-up rests on the limitations section,
not the achievements. Practitioners in statistical exchange have been solving
these problems for decades and will recognise overreach instantly. Naming the
bug I shipped, and the test that failed to catch it, is what earns the rest of it
a fair hearing.
