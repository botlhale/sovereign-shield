# Reference Provenance

Third-party publications retain their publishers' rights. The project's Apache licence does not relicense them or grant trademark rights. Public download availability does not establish unrestricted commercial redistribution.

| Artifact | Source | Role |
| --- | --- | --- |
| [checks_lbs.xls](checks_lbs.xls) | [BIS consistency workbook](https://www.bis.org/statistics/checks_lbs.xls) | Arithmetic rule source; 21 implemented within-dataset checks, six cross-collection entries not implemented |
| [dsd_lbs.pdf](dsd_lbs.pdf) | [BIS LBS structure guide](https://www.bis.org/statistics/dsd_lbs.pdf) | Human-readable reference, not runtime code validation |
| [bankstatsguide_tech.pdf](bankstatsguide_tech.pdf) | [BIS reporting guidelines](https://www.bis.org/statistics/bankstatsguide_tech.pdf) | Background reference |
| [Extracted DSD contract](../../src/reference_data/lbs_structure.json) | Versioned BIS REST URL and digest recorded in the file | Component IDs, codelist codes and attachment metadata; no prose publication reproduced |
| [JSON Schema](../../src/reference_data/sdmx_json_2_0.schema.json) | [SDMx-JSON 2.0.0 schema](https://json.sdmx.org/2.0.0/sdmx-json-data-schema.json) | Independent offline format validation; original schema content retained |

Review [BIS terms](https://www.bis.org/terms_conditions.htm) and the applicable SDMx artifact terms before bundling material in a commercial deliverable. Prefer source links and an approved local download step when redistribution rights are uncertain. The existing reference publications are retained pending that review, not declared cleared by this change. They are not included in the portal container allowlist. No historical rewrite or rights transfer is inferred.

Refresh metadata only through [the explicit helper](../../sh/refresh_lbs_contract.py), review the generated diff and rerun the contract tests. A pinned version can still have revised content; the source digest identifies what was inspected, and release review remains necessary.