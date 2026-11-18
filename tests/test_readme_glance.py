"""Every number in the README "Results at a glance" table is a runs.csv row.

Each table row names the facts it may quote. A fact is the latest runs.csv row for a
(metric, system, split, cohort), shown as `sec-agent report sync` shows it, plus its `n`.
A digit in a row that no named fact produces fails the test, and so does a named fact the row
leaves out. Where `results/gate/baseline.json` holds the same metric, the two files must agree.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from sec_agent.report.format import show_value
from sec_agent.report.latest import latest_rows, row_key
from sec_agent.runs import RunRow, read_runs

HEADING = "## Results at a glance"
COLUMNS = ["What was tested", "Result", "Why it matters"]
NUMBER = re.compile(r"\d+(?:\.\d+)?%?")


@dataclass(frozen=True)
class Fact:
    metric: str
    system: str
    split: str = "test"
    cohort: str = "none"
    show_n: bool = True


GLANCE: dict[str, list[Fact]] = {
    "Exact financial figures": [Fact("N1", "b2"), Fact("N1", "b0", show_n=False)],
    "Multi-step research tasks": [Fact("A1", "agent"), Fact("A1", "rag", show_n=False)],
    "Finding the right passage": [
        Fact("R1_mrr@10", "hybrid+rerank-ft"),
        Fact("R1_mrr@10", "hybrid", show_n=False),
    ],
    "Attacks and advice requests": [
        Fact("S1_attack_block", "guarded", split="none"),
        Fact("S1_advice_block", "guarded", split="none"),
        Fact("S1_false_refusal", "guarded", split="none"),
    ],
    "Automatic answer grader": [Fact("J1_kappa", "grader")],
    "Eval gate in CI": [Fact("G1", "eval-gate", split="none")],
}


def _glance_rows(readme: str) -> dict[str, list[str]]:
    assert HEADING in readme, f"README has no {HEADING!r} section"
    section = readme.split(HEADING, 1)[1].split("\n## ", 1)[0]
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    cells = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    assert cells
    assert cells[0] == COLUMNS
    return {row[0]: row for row in cells[2:]}


def _latest(repo_root: Path) -> dict[tuple[str, str, str, str], RunRow]:
    return {row_key(row): row for row in latest_rows(read_runs(repo_root / "runs.csv"))}


def _row_for(latest: dict[tuple[str, str, str, str], RunRow], fact: Fact) -> RunRow:
    key = (fact.metric, fact.system, fact.split, fact.cohort)
    assert key in latest, f"runs.csv has no row for {key}"
    return latest[key]


def _shown(row: RunRow, fact: Fact) -> list[str]:
    return [show_value(row), *([str(row.n)] if fact.show_n else [])]


@pytest.fixture(scope="module")
def readme_rows(repo_root: Path) -> dict[str, list[str]]:
    return _glance_rows((repo_root / "README.md").read_text("utf-8"))


def test_glance_table_has_exactly_the_checked_rows(readme_rows: dict[str, list[str]]) -> None:
    assert list(readme_rows) == list(GLANCE)
    assert all(len(row) == len(COLUMNS) for row in readme_rows.values())


@pytest.mark.parametrize("label", list(GLANCE))
def test_every_number_in_a_glance_row_comes_from_runs_csv(
    repo_root: Path, readme_rows: dict[str, list[str]], label: str
) -> None:
    latest = _latest(repo_root)
    allowed: list[str] = []
    for fact in GLANCE[label]:
        allowed += _shown(_row_for(latest, fact), fact)
    text = " | ".join(readme_rows[label])
    found = NUMBER.findall(text)
    assert [token for token in found if token not in allowed] == []
    assert [token for token in allowed if token not in found] == []


def test_glance_numbers_agree_with_the_gate_baseline(repo_root: Path) -> None:
    baseline = json.loads((repo_root / "results" / "gate" / "baseline.json").read_text("utf-8"))
    gate = {metric["name"]: metric for metric in baseline["metrics"]}
    latest = _latest(repo_root)
    checked = 0
    for facts in GLANCE.values():
        for fact in facts:
            entry = gate.get(f"{fact.metric}:{fact.system}")
            if entry is None:
                continue
            row = _row_for(latest, fact)
            assert entry["value"] == pytest.approx(row.value), fact
            assert entry["n"] == row.n, fact
            checked += 1
    # N1, A1, R1 and S1 facts are all in the gate baseline; J1 grader and G1 are not.
    assert checked == 9
