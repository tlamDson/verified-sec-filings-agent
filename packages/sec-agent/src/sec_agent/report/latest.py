"""Pick the rows to show: a re-run replaces the earlier row for the same key."""

from collections.abc import Sequence

from sec_agent.runs import RunRow

type Key = tuple[str, str, str, str]


def row_key(row: RunRow) -> Key:
    return (row.metric, row.system, row.split, row.cohort)


def latest_rows(rows: Sequence[RunRow]) -> list[RunRow]:
    """The last row for each (metric, system, split, cohort), in order of first appearance."""
    chosen: dict[Key, RunRow] = {}
    for row in rows:
        chosen[row_key(row)] = row
    return list(chosen.values())
