"""The committed runs.csv is valid against the runs schema."""

from pathlib import Path

from sec_agent.runs import RUNS_COLUMNS, read_runs


def test_runs_csv_header_matches_schema(repo_root: Path) -> None:
    header = (repo_root / "runs.csv").read_text("utf-8").splitlines()[0]
    assert tuple(header.split(",")) == RUNS_COLUMNS


def test_runs_csv_rows_validate(repo_root: Path) -> None:
    read_runs(repo_root / "runs.csv")
