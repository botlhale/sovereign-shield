# Synthetic Portal Capture Inventory

The current publication set uses screenshots supplied on **18 September 2026**.
Selected images were copied byte-for-byte from the local import folder into the
canonical filenames below; copy integrity was checked with SHA-256. Labels,
values, filters and display states were not redrawn or anonymized.

## Selected Captures

| Publication Asset | Supplied Source Filename | Displayed State |
| --- | --- | --- |
| [public_view.png](public_view.png) | `public_view.png` | Public, 13 published/free observations |
| [researcher_view.png](researcher_view.png) | `econ_researcher_view.png` | Researcher, 22 published observations, 9 masked measures |
| [researcher_gb_view.png](researcher_gb_view.png) | `econ_researcher_gb_rep_country_filter_view.png` | Researcher, reporting country GB, 14 observations, 4 masked measures |
| [submitter_ca_view.png](submitter_ca_view.png) | `regional_submitter_view.png` | CA submitter, Published mode, 14 observations |
| [submitter_us_view.png](submitter_us_view.png) | `regional_submitter_view2.png` | US submitter, Published mode, 17 observations |
| [submitter_ca_all_submissions.png](submitter_ca_all_submissions.png) | `regional_submitter_published+quarantine_view.png` | CA, Published + quarantine, 18 observations and submission feedback |
| [submitter_ca_quarantine_view.png](submitter_ca_quarantine_view.png) | `regional_submitter_quarantine_view.png` | CA, Quarantine only, 4 rejected observations and batch/observation feedback |
| [admin_published_view.png](admin_published_view.png) | `admin_view.png` | Administrator, Published mode, 22 observations with restricted measures visible |

The administrator capture is **not** the 44-row Published + quarantine mode.
That fixture outcome is documented in dated live evidence but requires its own
capture when presented visually. The older administrator/quarantine image is
superseded in the publication set; repository history preserves prior artifacts.

## Evidence Boundaries

Screenshots demonstrate the visible product state and synthetic disclosure labels.
They do not independently attest the authenticated identity, deployment commit,
full table contents beyond the visible scroll area, or statistical non-disclosure.
Submission timestamps are displayed record metadata, not capture timestamps.
Use [Release Evidence](../docs/RELEASE_EVIDENCE.md) for executable checks and limits.

The Analyst View reconciles expected latest filings with actual receiver IDs,
timestamps, values and verdicts. Current accepted publication is distinct from a
latest rejected filing. Researcher-visible row presence and published totals can
reconstruct masked measures; see the [open challenge](../SECURITY.md#statistical-reconstruction-challenge).

The modeled international input is SDMx files only. Synthetic bank micro-transactions
are educational calculation fixtures, not an institutional intake requirement or
system deliverable. All visible observations in this set belong to the synthetic
reference demonstration.

The sign-in/sign-out imports are excluded from the publication set because they
display account details and a password-entry screen without adding data-control
evidence. Original imports and newly supplied export files are not modified or
automatically published by screenshot selection. Existing [historical export samples](sdmx)
retain their own provenance.

## Use in Publications

[The persona demonstration](../docs/PERSONA_DEMO_SCRIPT.md#reference-captures) links
all selected views. The White Paper uses the public, researcher, CA combined and
administrator Published views, with captions matching their actual displayed state.
The Executive Brief and White Paper share the title **Bridging Public Dissemination
and Protected Data: A Zero-Trust SDMx Architecture on Azure Databricks**.