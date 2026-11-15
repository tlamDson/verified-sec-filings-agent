"""Schema and file I/O for runs.csv, the single source of every number in README and docs.

One row is one measured number: which metric, which system, on which split, for which
user cohort, with its sample size and confidence interval, at which git commit.
Simulated users never share a row with real users (`cohort`).
"""

import csv
import datetime as dt
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Cohort = Literal["real", "simulated", "none"]
Split = Literal["train", "dev", "test", "none"]


class RunRow(BaseModel):
    """One measured number. Field order is the column order of runs.csv."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: dt.date
    git_sha: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    metric: str = Field(min_length=1)
    system: str = Field(min_length=1)
    split: Split
    cohort: Cohort
    n: int = Field(ge=0)
    value: float
    unit: str = Field(min_length=1)
    ci_low: float | None = None
    ci_high: float | None = None
    index_version: str = ""
    config: str = ""
    notes: str = ""

    @field_validator("ci_low", "ci_high", mode="before")
    @classmethod
    def _blank_is_none(cls, raw: object) -> object:
        return None if raw == "" else raw

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.metric.startswith("U") and self.cohort == "none":
            raise ValueError("user metrics must name their cohort: real or simulated")
        if (self.ci_low is None) != (self.ci_high is None):
            raise ValueError("ci_low and ci_high must be given together")
        if (
            self.ci_low is not None
            and self.ci_high is not None
            and not self.ci_low <= self.value <= self.ci_high
        ):
            raise ValueError("value must lie inside its confidence interval")
        return self


RUNS_COLUMNS: tuple[str, ...] = tuple(RunRow.model_fields)


def read_runs(path: Path) -> list[RunRow]:
    """Read and validate every row; raise ValueError when the header is not RUNS_COLUMNS."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        if header != RUNS_COLUMNS:
            raise ValueError(f"runs.csv header {header} does not match {RUNS_COLUMNS}")
        return [RunRow.model_validate(record) for record in reader]


def append_run(path: Path, row: RunRow) -> None:
    """Append one row, writing the header first when the file is new or empty."""
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUNS_COLUMNS, lineterminator="\n")
        if needs_header:
            writer.writeheader()
        record = row.model_dump(mode="json")
        writer.writerow({key: "" if value is None else value for key, value in record.items()})
