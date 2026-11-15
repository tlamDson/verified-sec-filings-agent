"""The public demo: a Pages workflow on main builds the static site, and the README links it."""

from pathlib import Path
from typing import Any

import yaml

DEMO_URL = "https://tlamdson.github.io/verified-sec-filings-agent/"


def _text(repo_root: Path) -> str:
    return (repo_root / ".github" / "workflows" / "pages.yml").read_text("utf-8")


def _workflow(repo_root: Path) -> dict[Any, Any]:
    return yaml.safe_load(_text(repo_root))


def test_pages_deploys_on_main_only(repo_root: Path) -> None:
    # PyYAML reads the bare key `on` as True.
    triggers = _workflow(repo_root)[True]
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" not in triggers


def test_pages_builds_the_site_and_deploys_it_without_secrets(repo_root: Path) -> None:
    text = _text(repo_root)
    assert "sec-agent demo build" in text
    assert "actions/upload-pages-artifact" in text
    assert "actions/deploy-pages" in text
    assert "secrets." not in text


def test_pages_permissions_are_minimal(repo_root: Path) -> None:
    perms = _workflow(repo_root)["permissions"]
    assert perms == {"contents": "read", "pages": "write", "id-token": "write"}


def test_readme_links_the_demo_near_the_top(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text("utf-8")
    assert DEMO_URL in readme
    assert readme.index(DEMO_URL) < readme.index("## Results")
