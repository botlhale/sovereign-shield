"""Check repository-local Markdown links and render isolated publication proofs."""

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")


def slug(text):
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def children(tokens):
    for token in tokens:
        yield token
        yield from children(token.children or [])


def check_links():
    listed = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, check=True, text=True, capture_output=True).stdout
    paths = {ROOT / name for name in listed.splitlines() if name != "docs/solution_audit.md"}
    failures = []
    checked = 0
    for path in sorted(paths):
        if path.suffix.lower() != ".md" or not path.is_file():
            continue
        tokens = MARKDOWN.parse(path.read_text(encoding="utf-8"))
        for token in children(tokens):
            target = token.attrGet("href") if token.type == "link_open" else token.attrGet("src") if token.type == "image" else None
            if not target or urlsplit(target).scheme or target.startswith("//"):
                continue
            parts = urlsplit(target)
            destination = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            checked += 1
            exists = destination.is_file() and destination in paths
            exists |= destination.is_dir() and any(destination in candidate.parents for candidate in paths)
            if not exists:
                failures.append(f"{path.relative_to(ROOT)}: missing release file {target}")
            elif parts.fragment and destination.suffix.lower() == ".md" and not re.fullmatch(r"L\d+(?:-L\d+)?", parts.fragment):
                target_tokens = MARKDOWN.parse(destination.read_text(encoding="utf-8"))
                headings = {slug(target_tokens[index + 1].content.replace('`', '').replace('*', '')) for index, heading in enumerate(target_tokens[:-1]) if heading.type == "heading_open"}
                if unquote(parts.fragment) not in headings:
                    failures.append(f"{path.relative_to(ROOT)}: missing heading {target}")
    if failures:
        raise ValueError("\n".join(failures))
    print(f"Verified {checked} local Markdown links and heading anchors.")


def render_proofs():
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not chrome.is_file():
        raise RuntimeError("Chrome was not found; use your installed browser to proof the generated Markdown.")
    output = ROOT / ".pytest_cache" / "publication-proof"
    output.mkdir(parents=True, exist_ok=True)
    style = """@page { size:A4; margin:16mm; } body {font:10pt 'Segoe UI',sans-serif;line-height:1.45;color:#17242c;}
    h1{font-size:22pt;}h2{font-size:16pt;margin-top:20px;}h3{font-size:12pt;}h1,h2,h3{break-after:avoid;}
    img{display:block;max-width:100%;max-height:195mm;object-fit:contain;} table{border-collapse:collapse;width:100%;font-size:9pt;break-inside:avoid;}
    td,th{padding:6px;border:1px solid #ccd3d6;text-align:left;vertical-align:top;} pre{font-size:8pt;white-space:pre-wrap;overflow-wrap:anywhere;padding:10px;background:#f4f6f7;}
    a{color:#00685d;}blockquote{border-left:3px solid #168271;padding-left:10px;}p,li{orphans:3;widows:3;}"""
    sources = [ROOT / "docs/EXECUTIVE_BRIEF.md", ROOT / "docs/whitepaper/Bridging_Public_Dissemination_and_Protected_Data.md"]
    for source in sources:
        markup = '<!doctype html><html><head><meta charset="utf-8"><base href="' + source.parent.as_uri() + '/"><style>' + style + '</style></head><body>' + MARKDOWN.render(source.read_text(encoding="utf-8")) + '</body></html>'
        page = output / (source.stem + ".html")
        page.write_text(markup, encoding="utf-8")
        pdf = page.with_suffix(".pdf")
        subprocess.run([str(chrome), "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={output / (source.stem + '-profile')}", f"--print-to-pdf={pdf}", page.as_uri()], capture_output=True, text=True, timeout=60, check=True)
        from pypdf import PdfReader
        pages = PdfReader(str(pdf)).pages
        print(f"{source.name}: {len(pages)} proof pages -> {pdf.relative_to(ROOT)}")
        if source.name == "EXECUTIVE_BRIEF.md" and len(pages) != 8:
            raise ValueError("The executive brief must fit its eight designed pages.")
        if source.name != "EXECUTIVE_BRIEF.md":
            for number in range(1, 11):
                matches = [page for page in pages if re.search(rf"Figure\s+{number}\s", page.extract_text())]
                if len(matches) != 1 or not len(matches[0].images):
                    raise ValueError(f"Figure {number} does not share its page with an image.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-proof", action="store_true")
    args = parser.parse_args()
    check_links()
    if args.print_proof:
        render_proofs()