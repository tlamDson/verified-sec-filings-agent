"""runs.csv schema: the single source for every number shown in README and docs."""

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from sec_agent.runs import RUNS_COLUMNS, RunRow, append_run, read_runs


def _row(**overrides: object) -> RunRow:
    fields: dict[str, object] = {
        "date": date(2026, 11, 13),
        "git_sha": "f2c723b",
        "metric": "N1",
        "system": "b2",
        "split": "test",
        "cohort": "none",
        "n": 300,
        "value": 0.8,
        "unit": "fraction",
        "ci_low": 0.755,
        "ci_high": 0.845,
        "index_version": "v1",
        "config": "default",
        "notes": "",
    }
    fields.update(overrides)
    return RunRow.model_validate(fields)


def test_columns_follow_field_order() -> None:
    assert RUNS_COLUMNS == tuple(RunRow.model_fields)


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "runs.csv"
    first = _row()
    second = _row(metric="U1", cohort="simulated", value=42, unit="sessions", ci_low=None, ci_high=None)
    append_run(path, first)
    append_run(path, second)
    assert read_runs(path) == [first, second]
    assert path.read_text("utf-8").splitlines()[0] == ",".join(RUNS_COLUMNS)


def test_read_rejects_wrong_header(tmp_path: Path) -> None:
    path = tmp_path / "runs.csv"
    path.write_text("date,value\n", "utf-8")
    with pytest.raises(ValueError, match="header"):
        read_runs(path)


def test_header_only_file_has_no_rows(tmp_path: Path) -> None:
    path = tmp_path / "runs.csv"
    path.write_text(",".join(RUNS_COLUMNS) + "\n", "utf-8")
    assert read_runs(path) == []


@pytest.mark.parametrize("cohort", ["sim", "users", ""])
def test_rejects_unknown_cohort(cohort: str) -> None:
    with pytest.raises(ValidationError):
        _row(cohort=cohort)


def test_user_metrics_must_name_their_cohort() -> None:
    with pytest.raises(ValidationError, match="cohort"):
        _row(metric="U1", cohort="none")


@pytest.mark.parametrize("sha", ["xyz1234", "abc", "F2C723B"])
def test_rejects_bad_git_sha(sha: str) -> None:
    with pytest.raises(ValidationError):
        _row(git_sha=sha)


def test_rejects_half_interval() -> None:
    with pytest.raises(ValidationError, match="ci_low and ci_high"):
        _row(ci_high=None)


def test_rejects_value_outside_interval() -> None:
    with pytest.raises(ValidationError, match="interval"):
        _row(value=0.9)


def test_rejects_negative_n() -> None:
    with pytest.raises(ValidationError):
        _row(n=-1)
