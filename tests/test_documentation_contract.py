from pathlib import Path
import hashlib
import json
import re
from xml.etree import ElementTree

import pytest


ROOT = Path(__file__).resolve().parents[1]
WHITEPAPER = ROOT / "docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md"
PRINT_GROUP = re.compile(r'<div style="page-break-inside: avoid;">\s*(.*?)\s*</div>', re.DOTALL)
IMAGE_LINK = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
SECTION_BREAK = '<div style="page-break-after: always;"></div>'
FIGURES = [
    "../figures/executive_architecture.png",
    "../figures/engagement_boundary.png",
    "../figures/dual_consumption.png",
    "../figures/triple_lock.png",
    "../../demo/public_view.png",
    "../../demo/researcher_view.png",
    "../../demo/submitter_ca_all_submissions.png",
    "../../demo/admin_published_view.png",
    "../figures/submission_history.png",
    "../figures/compute_strategy.png",
]


def test_whitepaper_figures_are_sequential_and_print_grouped():
    paper = WHITEPAPER.read_text(encoding="utf-8")
    image_groups = [group for group in PRINT_GROUP.findall(paper) if IMAGE_LINK.search(group)]

    assert IMAGE_LINK.findall(paper) == FIGURES
    assert len(image_groups) == len(FIGURES)
    for number, (group, target) in enumerate(zip(image_groups, FIGURES), start=1):
        assert IMAGE_LINK.findall(group) == [target]
        assert re.search(rf'\)\s*\*Figure {number} \u2014 [^\n]+\*\s*$', group)
        assert (WHITEPAPER.parent / target).is_file()


def test_whitepaper_tables_and_sql_stay_inside_print_groups():
    paper = WHITEPAPER.read_text(encoding="utf-8")
    outside_groups = PRINT_GROUP.sub("", paper)

    assert not IMAGE_LINK.search(outside_groups)
    assert not re.search(r"^```sql|^\|", outside_groups, re.MULTILINE)
    assert paper.count("```sql") == 2
    assert paper.index("## Appendix A:") < paper.index("```sql")
    assert len(re.findall(r'^\| Schema |^\| Persona ', paper, re.MULTILINE)) == 2


def test_whitepaper_major_sections_keep_explicit_page_breaks():
    paper = WHITEPAPER.read_text(encoding="utf-8")
    sections = paper.split(SECTION_BREAK)

    assert len(sections) == 7
    for number, section in enumerate(sections[:6], start=1):
        assert re.search(rf"^## {number}\. ", section, re.MULTILINE)
    assert re.search(r"^## Conclusion$", sections[-1], re.MULTILINE)


def test_public_notices_and_whitepaper_affiliation_match():
    paper = WHITEPAPER.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notice = re.compile(r"^> \*\*Independent Reference Architecture Notice:\*\*\s*\n> ([^\n]+)", re.MULTILINE)
    paper_notice = notice.search(paper)
    readme_notice = notice.search(readme)

    assert paper_notice is not None and readme_notice is not None
    assert paper_notice.group(1) == readme_notice.group(1)
    assert paper_notice.end() < paper.index("## 1.")
    assert "developed in a personal capacity using synthetic data fixtures" in paper_notice.group(1)
    assert "**Affiliation:** Independent Reference Architecture" in paper
    assert "**Organization:**" not in paper


def test_all_submitter_reference_captures_are_linked():
    guide = (ROOT / "docs/PERSONA_DEMO_SCRIPT.md").read_text(encoding="utf-8")
    for name in (
        "public_view.png",
        "researcher_view.png",
        "researcher_gb_view.png",
        "submitter_ca_view.png",
        "submitter_ca_all_submissions.png",
        "submitter_ca_quarantine_view.png",
        "submitter_us_view.png",
        "admin_published_view.png",
    ):
        image = ROOT / "demo" / name
        assert image.is_file() and image.stat().st_size > 0
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert f"../demo/{name}" in guide


def test_administrator_capture_caption_matches_published_mode():
    paper = WHITEPAPER.read_text(encoding="utf-8")
    caption = re.search(r"\*Figure 8[^\n]+", paper).group(0)
    assert "Published View" in caption and "22 observations" in caption
    assert "does not show" in caption


def test_executive_brief_and_whitepaper_share_publication_title():
    brief = (ROOT / "docs/EXECUTIVE_BRIEF.md").read_text(encoding="utf-8")
    paper = WHITEPAPER.read_text(encoding="utf-8")
    brief_title = re.search(r"^# (.+)$", brief, re.MULTILINE)
    paper_title = re.search(r"^# (.+)$", paper, re.MULTILINE)
    assert brief_title is not None and paper_title is not None
    assert brief_title.group(1) == paper_title.group(1)


@pytest.mark.parametrize("relative_path", [
    "README.md",
    "docs/EXECUTIVE_BRIEF.md",
    "docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md",
])
def test_primary_publications_preserve_enterprise_scope(relative_path):
    content = (ROOT / relative_path).read_text(encoding="utf-8")
    prose = re.sub(r"\s+", " ", content)
    assert "Analyst View" in prose
    assert "educational" in prose and "system deliverable" in prose
    assert "latest" in prose and "accepted" in prose
    assert "technology-agnostic" in prose
    assert all(platform in prose for platform in ("AWS", "GCP", "Microsoft Fabric", "open-source"))
    assert "reconstruct" in prose.lower()
    assert re.search(r"restrict|remov", prose, re.IGNORECASE)
    assert all(measure in prose for measure in ("75 minutes", "30 minutes", "US$10"))
    assert "prerequisite" in prose


def test_documentation_avoids_author_centric_architecture_claims():
    paths = list(ROOT.glob("*.md")) + list((ROOT / "docs").rglob("*.md")) + list((ROOT / ".github/skills").glob("*.md"))
    forbidden = re.compile(
        r"\b(?:the author claims|author reports|I architected|I implemented|I established|I enforced|I mention|no longer used)\b",
        re.IGNORECASE,
    )
    for path in paths:
        prose = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
        assert not forbidden.search(prose), path.relative_to(ROOT)


def test_engagement_and_publication_guides_keep_approval_boundaries():
    engagement = (ROOT / "docs/ENTERPRISE_ONBOARDING_PLAYBOOK.md").read_text(encoding="utf-8")
    publication = (ROOT / "docs/PUBLICATION_AND_RELEASE.md").read_text(encoding="utf-8")
    assert all(section in engagement for section in (
        "Repository Options", "Client Prerequisites", "Handover Package", "Offboarding and Continuity",
    ))
    assert "ENGAGEMENT_WORKFLOW_IMAGE_PROMPT.md" in engagement
    assert all(topic in publication for topic in ("Zenodo", "Figshare", "SSRN", "AI disclosure", "--verify-tag", "--draft", "--prerelease"))
    assert "typically not accepted" in publication
    assert "not executed external actions" in publication


def test_publication_diagrams_match_their_source_manifest():
    manifest = json.loads((ROOT / "docs/figures/manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 6
    for item in manifest:
        source = ROOT / item["source"]
        image = ROOT / item["image"]
        assert hashlib.sha256(source.read_text(encoding="utf-8").encode("utf-8")).hexdigest() == item["source_sha256"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == item["image_sha256"]
        root = ElementTree.parse(source).getroot()
        assert root.attrib["width"] == "1600" and root.attrib["height"] == "900"
        assert root.find("{http://www.w3.org/2000/svg}title") is not None
        assert root.find("{http://www.w3.org/2000/svg}desc") is not None