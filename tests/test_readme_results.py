"""README results, the bullets and the design doc agree with runs.csv."""

from pathlib import Path

from sec_agent.report.bullets import render_bullets
from sec_agent.report.render import render_results
from sec_agent.report.splice import splice_block
from sec_agent.runs import read_runs


def test_readme_results_block_is_rendered_from_runs_csv(repo_root: Path) -> None:
    rows = read_runs(repo_root / "runs.csv")
    readme = (repo_root / "README.md").read_text("utf-8")
    assert splice_block(readme, render_results(rows)) == readme


def test_bullets_file_is_rendered_from_runs_csv(repo_root: Path) -> None:
    rows = read_runs(repo_root / "runs.csv")
    assert (repo_root / "docs" / "bullets.md").read_text("utf-8") == render_bullets(rows)


def test_readme_says_what_is_not_measured_and_links_the_design(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text("utf-8")
    assert "Status: being built" not in readme
    assert "docs/design.md" in readme
    assert "simulated" in readme.lower()


def test_design_doc_is_the_final_version(repo_root: Path) -> None:
    design = (repo_root / "docs" / "design.md").read_text("utf-8")
    assert "Version 0 (scaffold)" not in design
    assert "No row exists yet" not in design
    assert "## Results" in design
    assert "runs.csv" in design
