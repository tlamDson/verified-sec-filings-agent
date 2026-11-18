"""The README is recruiter-first; setup and the full results move to DEVELOPMENT.md."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = Path(".github") / "readme" / "architecture.svg"
SECTIONS = [
    "## What it does",
    "## Results at a glance",
    "## What I built",
    "## Tech stack",
    "## Quick start",
]
DIAGRAM_LABELS = [
    "SEC EDGAR",
    "XBRL facts",
    "Postgres",
    "text index",
    "retrieval",
    "figure lookup",
    "citation check",
    "advice refusal",
    "FastAPI",
    "Hugging Face Spaces",
    "web app",
    "golden questions",
    "judge",
    "CI gate",
]


def _readme(repo_root: Path) -> str:
    return (repo_root / "README.md").read_text("utf-8")


def test_readme_sections_are_in_order(repo_root: Path) -> None:
    readme = _readme(repo_root)
    positions = [readme.index(heading) for heading in SECTIONS]
    assert positions == sorted(positions)


def test_readme_top_has_pitch_badges_and_diagram_before_any_section(repo_root: Path) -> None:
    readme = _readme(repo_root)
    top = readme.split("\n## ", 1)[0]
    assert top.startswith("# Verified SEC Filings Agent\n")
    assert "actions/workflows/ci.yml/badge.svg" in top
    assert "License" in top
    assert "LICENSE" in top
    assert "Live demo: coming soon" in top
    assert "vercel.app" not in readme
    image = re.search(r"!\[([^\]]+)\]\(\.github/readme/architecture\.svg\)", top)
    assert image is not None
    assert len(image.group(1)) > 40, "diagram needs real alt text"


def test_readme_has_no_mermaid_and_only_the_diagram_image(repo_root: Path) -> None:
    readme = _readme(repo_root)
    development = (repo_root / "DEVELOPMENT.md").read_text("utf-8")
    assert "mermaid" not in readme.lower()
    assert "mermaid" not in development.lower()
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
    non_badges = [src for src in images if "badge" not in src and "shields.io" not in src]
    assert non_badges == [".github/readme/architecture.svg"]


def test_readme_what_it_does_has_three_bullets_and_links_development(repo_root: Path) -> None:
    readme = _readme(repo_root)
    section = readme.split("## What it does", 1)[1].split("\n## ", 1)[0]
    assert len([line for line in section.splitlines() if line.startswith("- ")]) == 3
    assert "(DEVELOPMENT.md)" in readme


def test_development_holds_the_moved_sections(repo_root: Path) -> None:
    development = (repo_root / "DEVELOPMENT.md").read_text("utf-8")
    for heading in ["### Web app and API", "### Simulated users", "## Contributing"]:
        assert heading in development
    assert "<!-- results:start -->" in development
    assert "<!-- results:start -->" not in _readme(repo_root)


def test_architecture_svg_is_plain_and_fits_github(repo_root: Path) -> None:
    text = (repo_root / SVG).read_text("utf-8")
    root = ET.fromstring(text)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert float(root.attrib["width"]) <= 900
    lowered = text.lower().replace('xmlns="http://www.w3.org/2000/svg"', "")
    for banned in ["<script", "<image", "<foreignobject", "@import", "@font-face", "http"]:
        assert banned not in lowered, banned
    background = root.find("{http://www.w3.org/2000/svg}rect")
    assert background is not None
    assert background.attrib.get("fill", "").lower() in {"#fff", "#ffffff", "white"}
    assert float(background.attrib.get("rx", "0")) > 0
    words = " ".join(
        "".join(node.itertext()) for node in root.iter("{http://www.w3.org/2000/svg}text")
    )
    for label in DIAGRAM_LABELS:
        assert label in words, label
