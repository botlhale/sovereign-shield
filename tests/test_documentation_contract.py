from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WHITEPAPER = ROOT / "docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md"
PRINT_GROUP = re.compile(r'<div style="page-break-inside: avoid;">\s*(.*?)\s*</div>', re.DOTALL)
IMAGE_LINK = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
SECTION_BREAK = '<div style="page-break-after: always;"></div>'
FIGURES = [
    "../sovereign-shield_executive.jpg",
    "../the_contractor_dilemma.png",
    "../dual_consumption_model.png",
    "../triple-lock-architecture.png",
    "../../demo/public_view.png",
    "../../demo/researcher_view.png",
    "../../demo/submitter_ca_all_submissions.png",
    "../../demo/admin_view_with_quarantine_data.png",
    "../scd2.png",
    "../scale_strategy.png",
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
        "submitter_ca_view.png",
        "submitter_ca_all_submissions.png",
        "submitter_us_view.png",
    ):
        image = ROOT / "demo" / name
        assert image.is_file() and image.stat().st_size > 0
        assert f"../demo/{name}" in guide