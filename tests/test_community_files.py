"""The GitHub community profile files exist, stay short and hold no personal contact data."""

import re
from pathlib import Path

import pytest

COMMUNITY_FILES = (
    "CONTRIBUTING.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    ".github/pull_request_template.md",
)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")


@pytest.mark.parametrize("name", COMMUNITY_FILES)
def test_community_file_is_short_and_has_no_contact(repo_root: Path, name: str) -> None:
    text = (repo_root / name).read_text("utf-8")
    assert 0 < len(text.splitlines()) <= 60
    assert not EMAIL.search(text), name
    assert not PHONE.search(text), name


def test_contributing_names_branch_flow_and_checks(repo_root: Path) -> None:
    text = (repo_root / "CONTRIBUTING.md").read_text("utf-8")
    for phrase in ("README.md", "develop", "Python checks", "Web checks", "pytest", "pnpm test"):
        assert phrase in text, phrase


@pytest.mark.parametrize(
    ("name", "label"),
    [("bug_report.md", "bug"), ("feature_request.md", "enhancement")],
)
def test_issue_templates_have_front_matter(repo_root: Path, name: str, label: str) -> None:
    text = (repo_root / ".github/ISSUE_TEMPLATE" / name).read_text("utf-8")
    front = text.split("---")[1]
    for key in ("name:", "about:", "title:", "labels:"):
        assert key in front, key
    assert label in front


def test_pr_template_targets_develop_and_tdd(repo_root: Path) -> None:
    text = (repo_root / ".github/pull_request_template.md").read_text("utf-8")
    for phrase in ("develop", "failing tests", "runs.csv"):
        assert phrase in text, phrase
