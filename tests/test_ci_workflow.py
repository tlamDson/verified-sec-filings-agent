"""The CI workflow exposes the two required checks under their exact names."""

from pathlib import Path
from typing import Any

import yaml


def _workflow(repo_root: Path) -> dict[Any, Any]:
    return yaml.safe_load((repo_root / ".github" / "workflows" / "ci.yml").read_text("utf-8"))


def test_job_names_match_required_checks(repo_root: Path) -> None:
    names = {job["name"] for job in _workflow(repo_root)["jobs"].values()}
    assert names == {"Python checks", "Web checks"}


def test_runs_on_pull_requests_and_develop(repo_root: Path) -> None:
    # PyYAML reads the bare key `on` as True.
    triggers = _workflow(repo_root)[True]
    assert "pull_request" in triggers
    assert "develop" in triggers["push"]["branches"]


def _steps(repo_root: Path, job_name: str) -> str:
    for job in _workflow(repo_root)["jobs"].values():
        if job["name"] == job_name:
            return "\n".join(step.get("run", "") for step in job["steps"])
    raise AssertionError(f"no job named {job_name}")


def test_python_job_runs_lint_types_tests(repo_root: Path) -> None:
    run = _steps(repo_root, "Python checks")
    for command in ("uv sync --locked", "ruff check", "ruff format --check", "pyright", "pytest"):
        assert command in run


def test_web_job_runs_lint_types_tests(repo_root: Path) -> None:
    run = _steps(repo_root, "Web checks")
    for command in (
        "pnpm install --frozen-lockfile",
        "pnpm biome ci",
        "pnpm typecheck",
        "pnpm test",
    ):
        assert command in run
