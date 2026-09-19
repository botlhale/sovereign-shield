# Publication Venues and GitHub Release

**Recommendation:** use Zenodo as the primary citable home for the current White
Paper and Executive Brief, with a versioned GitHub Release for code and evidence.
Figshare is the second archival option for an eligible reusable research output,
not a second DOI deposit of the same already published paper. LinkedIn provides
professional discovery; neither an archive deposit nor a GitHub release is peer review.

The shared publication title is **Bridging Public Dissemination and Protected Data:
A Zero-Trust SDMx Architecture on Azure Databricks**. Formats are identified
separately as Executive Brief and White Paper. Author, company stewardship,
licensing rights and institutional affiliation remain distinct.

Official platform requirements below were checked on **18 September 2026**. Recheck
the linked policies at submission, particularly eligibility and license options.

## 1. Zenodo: Primary Archival Recommendation

**Fit:** a versioned technical report with reproducible synthetic architecture
evidence, persistent citation and related software links. It accepts research
outputs beyond conventional journal articles. It does not certify the technical
claims or confer journal acceptance.

**Requirements:** an account; rights to every uploaded file; a suitable resource
type; title, publication date, creators and the form's required metadata; an
accurate description and approved license. Include ORCID where available, subject
keywords, version and related repository/release identifiers. The current upload
guide allows up to 100 files and 50 GB per record. Public metadata must not contain
confidential client information even if file access is restricted.

### Steps

1. Create/sign in to a Zenodo account and select **New upload**. Treat the White
   Paper as the primary report and the Executive Brief as its clearly labelled
   companion file; do not package third-party reference PDFs/workbooks without rights.
2. Select the publication/report resource type offered by the form. Enter the
   exact shared title, author Botlhale Mosweu, actual affiliation/personal-capacity
   information, date and version. Identify Augmenta Systems as steward separately
   where metadata supports it; do not add an employer as sponsor or coauthor.
3. Add an abstract/description covering method, synthetic scope, implementation,
   observed lifecycle results and limits. Include SDMx, information architecture,
   statistical disclosure, data governance and infrastructure-as-code keywords.
   Link the specific tested code version and release evidence.
4. If this exact object has no DOI, reserve one using **Get a DOI now**, insert it
   into the final PDFs, then upload those files. If it already has a DOI, use the
   existing DOI according to Zenodo's guidance rather than minting another.
   A software release or supporting dataset is a different object and should not
   reuse the paper's DOI.
5. Select a rights-approved license, set visibility, save the draft and preview
   all metadata/files. Existing Apache licensing does not relicense third-party
   artifacts; no new document license or ownership assignment is implied here.
6. Publish and verify the DOI landing page and downloads. Cite the version-specific
   record for reproducibility. Use **New version** for substantive revisions and
   link versions; update the LinkedIn Featured link and GitHub release notes.

Zenodo currently permits self-service file corrections within 45 days of publication;
metadata can be edited separately. Prefer explicit new versions for substantive
changes rather than silently changing a cited result. A reserved DOI is registered
only on publication, and deleting its draft loses the reservation.

Sources: [create/upload/publish](https://help.zenodo.org/docs/deposit/create-new-upload/),
[metadata](https://help.zenodo.org/docs/deposit/describe-records/),
[DOI handling](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/),
[versioning](https://help.zenodo.org/docs/deposit/manage-versions/).

## 2. Figshare: Alternative Research-Output Archive

**Fit:** reusable original research outputs, such as this technical reference with
methods, synthetic evidence and reusable diagrams. Use it as an alternative to
Zenodo, or for a distinct supporting artifact linked to the canonical paper.
The free platform excludes product promotion and content without research reuse
value; it is not a consulting marketing host or a duplicate-publication service.

**Requirements:** a verified email/account, ownership or permission to publish,
no sensitive data, appropriate item type, the form's required metadata, an explicit
license and compliance with moderation/acceptable-use rules. On individual accounts,
**Report is not a default item type**. Use an accurate available type such as
Online resource for this reference output, or a client/institutional Report type
where enabled; do not label it a peer-reviewed Journal contribution. Preprint is
appropriate only for a genuine research manuscript awaiting formal publication.

### Steps

1. Confirm that the output is reusable research material and has not already been
   published with a DOI elsewhere. Choose Figshare instead of a duplicate Zenodo
   deposit, or select a genuinely distinct supporting artifact.
2. Create/verify the account, optionally connect ORCID, then open **My content >
   Items > Create a new**. Choose the correct available item type and upload the
   rights-cleared PDF or supporting files.
3. Enter the shared title for the paper, named authors, description/methods,
   version/date, specific keywords and related materials. Choose suitable subject
   categories; mandatory fields depend on the item/account configuration.
4. Select the approved license deliberately. Dataset defaults must not be treated
   as authorization to waive rights in a document or third-party artwork. Add the
   related code release and evidence links using the appropriate relation type.
5. Reserve a DOI if needed, include it in the final file, and review metadata,
   previews, privacy and terms before **Publish**. An institutional repository may
   require review rather than immediate publication.
6. Verify the public landing page and citation. File replacement or other substantive
   changes create a new version; cite a version DOI for fixed evidence. Do not
   assume a published research output can simply be withdrawn without a record.

The free-platform policy excludes already-published objects with an existing DOI.
Some institutional accounts can manage existing identifiers, but that is not a
general individual-account permission. Seek support before an ambiguous deposit.

Sources: [metadata and publication steps](https://info.figshare.com/user-guide/how-to-fill-in-the-metadata-fields-first-step/),
[item types](https://info.figshare.com/user-guide/item-types/),
[DOI reservation](https://info.figshare.com/user-guide/how-to-reserve-a-doi/),
[versioning](https://info.figshare.com/user-guide/how-versioning-works/),
[copyright and acceptable use](https://info.figshare.com/user-guide/figshare-policies/).

## Why SSRN Is Not the First Destination for This Version

SSRN is relevant to economic and information-systems research, but its **3 August
2026 submission guidelines** list frameworks and how-to guides among content
typically not accepted. They require rigorous methodology and original findings.
The current architectural White Paper must not be presented as an accepted
economic research article or submitted on the assumption that every white paper qualifies.

For a later research manuscript, first define a research question, related-work
comparison, reproducible method, original findings, uncertainty and limitations.
The existing synthetic control evidence can support that work; it does not prove
economic savings, institutional outcomes or global novelty.

An eligible SSRN submission requires a complete author profile, English title and
abstract, written date, full English PDF displaying authors/affiliations, valid
author contact details, permissions, and an **AI disclosure in both the abstract
and PDF when AI was used**. Organizational authors are generally disallowed
except specified government/academic cases. Review the current rules and submit
through SSRN's form only after preparing that scholarly version. Screening is
not peer review and acceptance is not guaranteed; some processing can take up to
10 business days.

Sources: [submission guidelines](https://www.elsevier.support/ssrn/answer/get-started),
[submission form guide](https://www.elsevier.support/ssrn/news/submission-form),
[review process](https://www.elsevier.support/ssrn/answer/ssrn-review-process).

## GitHub Release, Not a Package

Use a **GitHub Release** for the architecture: a reviewed source revision/tag,
release notes, PDF publications, reproducibility evidence and checksums. Terraform
and Databricks bundles are source/configuration artifacts, not a package ecosystem
served directly by GitHub Packages.

GitHub Packages is appropriate later for a separately supported OCI/Docker portal
image in GHCR. That requires image builds, dependency/security review, versioning,
digest pinning, authentication and maintenance. It does not replace the architecture
release. Terraform modules can be referenced by a pinned Git tag or published to
a suitable Terraform registry when their reusable interface is ready.

### Exact Release Steps

1. **Review and freeze.** Select the approved commit. Run offline tests, documentation
   checks and applicable Terraform/PowerShell gates; record actual live evidence
   separately. Review the automatic source archive as well as attached PDFs for
   secrets, client material and third-party redistribution rights. A pre-release
   label does not waive these requirements.
2. **Prepare artifacts.** Render and review the PDFs. Record the tested commit,
   environment, limits and [measurement provenance](RELEASE_EVIDENCE.md#reference-evaluation-metrics).
   A diagram or screenshot is not independent control certification.

```powershell
.venv\Scripts\python.exe -m pytest tests/
.venv\Scripts\python.exe sh/verify_docs.py --render-diagrams --print-proof
git diff --check
git status --short
git rev-parse HEAD
```

3. **Choose an unused version tag.** The example `v0.1.0` is a suggested initial
   reference release, not an existing or automatically approved tag. Confirm the
   selected commit is reviewed and pushed, then create/push the annotated tag:

```powershell
$releaseCommit = git rev-parse HEAD
$tag = 'v0.1.0'
git tag --list $tag
git tag -a $tag $releaseCommit -m 'SovereignShield synthetic reference release'
git push origin $tag
```

4. **Create a draft pre-release with both PDFs.** Authenticate GitHub CLI directly
   as the authorized maintainer; never paste a token into source or chat. Check
   current filenames and the release evidence before running:

```powershell
$briefPdf = '.pytest_cache/publication-proof/EXECUTIVE_BRIEF.pdf'
$paperPdf = '.pytest_cache/publication-proof/Bridging_Public_Dissemination_and_Protected_Data.pdf'
Get-FileHash -Algorithm SHA256 -Path $briefPdf, $paperPdf
gh release create $tag $briefPdf $paperPdf `
  --repo botlhale/sovereign-shield `
  --verify-tag --draft --prerelease `
  --title "SovereignShield $tag: Synthetic Reference Architecture" `
  --notes-file docs/RELEASE_EVIDENCE.md
```

5. **Review the draft.** In **Repository > Releases**, inspect tag/commit, PDF
   downloads, source ZIP/tarball, checksums, dependency/provenance inventory,
   migration warning and known disclosure limitations. Add a concise release
   summary and canonical paper DOI when it exists. Attach all assets before
   publishing if immutable releases are enabled.
6. **Publish deliberately.** Click **Publish release**, or run:

```powershell
gh release edit $tag --repo botlhale/sovereign-shield --draft=false
gh release view $tag --repo botlhale/sovereign-shield
```

Verify the public release and artifact links, then use them in the archival record
and LinkedIn Featured section. Do not force-move a published tag; issue a new
version for changed code or evidence. Mark the release as a synthetic reference,
not production accreditation.

Sources: [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository),
[release-create CLI](https://cli.github.com/manual/gh_release_create),
[GitHub Packages scope](https://docs.github.com/en/packages/learn-github-packages/introduction-to-github-packages).

## Approval Boundary

These are publication instructions, not executed external actions. DOI registration,
third-party licensing choices, repository/tag pushes, public release and social
posting require author/rights-holder approval. The current source-license and
copyright notices are unchanged. Prepare any required AI-assistance statement
truthfully and have the responsible author approve it before submission.