"""docs/design.md: the first system-design write-up."""

from pathlib import Path

REQUIRED_SECTIONS = (
    "## Requirements",
    "## Capacity estimates",
    "## Architecture",
    "## Distributed concerns",
    "## Failure modes",
    "## Edge-case rules",
    "## Non-goals",
)


def test_design_doc_has_required_sections(repo_root: Path) -> None:
    text = (repo_root / "docs" / "design.md").read_text("utf-8")
    for heading in REQUIRED_SECTIONS:
        assert heading in text, heading


def test_design_doc_lists_every_edge_case(repo_root: Path) -> None:
    text = (repo_root / "docs" / "design.md").read_text("utf-8")
    for n in range(1, 13):
        assert f"| E{n} |" in text, f"E{n}"
