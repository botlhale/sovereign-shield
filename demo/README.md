# Synthetic Portal Capture Inventory

Eight captures were supplied on **18 September 2026** and copied byte-for-byte into the
canonical filenames below; copy integrity was checked with SHA-256. Labels, values,
filters and display states were not redrawn or anonymized. They predate coordinate
masking, so their researcher views still show exact keys for restricted rows.

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

The administrator capture is **not** the 44-row Published + quarantine mode; that
outcome is documented in dated live evidence and needs its own capture.

## Discovery Gateway Capture

[researcher_discovery_view.png](researcher_discovery_view.png) was rendered on
**1 October 2026** from the local synthetic catalog: 22 published observations, nine
restricted values shown as *restricted* and their keys ending in `.xx.xx` in the same
muted style. The persona is a labelled browser fixture over the local policy mirror,
not live SSO. Reproduce it at 1440x900 with:

```bash
python sh/local_demo.py --serve researcher --port 8765
google-chrome --headless --hide-scrollbars --window-size=1440,900 \
  --virtual-time-budget=10000 --screenshot=researcher_discovery_view.png http://127.0.0.1:8765/
```

## Evidence Boundaries

Screenshots demonstrate visible product state. They do not attest the authenticated
identity, deployment commit, rows beyond the visible scroll area or statistical
non-disclosure. Submission timestamps are record metadata, not capture times. Use
[Release Evidence](../docs/RELEASE_EVIDENCE.md) for executable checks and limits.
Sign-in and sign-out imports are excluded because they show account details and a
password screen. The [historical export samples](sdmx) keep their own provenance.

The [persona demonstration](../docs/PERSONA_DEMO_SCRIPT.md#reference-captures) links
every capture. The White Paper uses the public, Discovery Gateway, CA combined and
administrator views, with captions that match their displayed state.
