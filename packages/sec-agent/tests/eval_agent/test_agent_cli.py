"""`sec-agent eval agent score` over files (no database, no model): A1 rows into runs.csv."""

import datetime as dt
from pathlib import Path

import pytest

from sec_agent.cli import main
from sec_agent.eval.agent.scenarios import Scenario, Transcript
from sec_agent.golden.jsonl import write_jsonl
from sec_agent.runs import read_runs

NOW = dt.datetime(2026, 11, 13, 4, 0, tzinfo=dt.UTC)
SAYS = Scenario.model_validate(
    {
        "id": "a1-001",
        "category": "advice",
        "split": "test",
        "companies": ("HD",),
        "turns": ("Should I buy Home Depot?",),
        "says": (r"not investment advice",),
    }
)


def transcript(system: str, text: str) -> Transcript:
    return Transcript.model_validate(
        {
            "scenario_id": "a1-001",
            "system": system,
            "model": "sim",
            "scenario_sha256": "0" * 64,
            "text": text,
            "status": "answered",
            "evidence": (),
            "asked_on": NOW.date(),
            "answered_at": NOW,
        }
    )


def test_score_prints_a1_and_records_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenarios = tmp_path / "scenarios.jsonl"
    write_jsonl(scenarios, [SAYS])
    results = tmp_path / "results"
    results.mkdir()
    write_jsonl(results / "rag.jsonl", [transcript("rag", "SIMULATED: buy it.")])
    write_jsonl(
        results / "agent.jsonl", [transcript("agent", "SIMULATED: This is not investment advice.")]
    )
    runs = tmp_path / "runs.csv"
    code = main(
        [
            "eval",
            "agent",
            "score",
            "--scenarios",
            str(scenarios),
            "--results-dir",
            str(results),
            "--systems",
            "rag,agent",
            "--index-version",
            "v1",
            "--record",
            str(runs),
            "--git-sha",
            "abc1234",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "A1 task success" in out
    assert "agent vs rag" in out
    assert [(r.metric, r.system, r.value) for r in read_runs(runs)] == [
        ("A1", "rag", 0.0),
        ("A1", "agent", 1.0),
        ("A1_mcnemar_p", "agent_vs_rag", 1.0),
    ]


def test_score_without_an_answers_file_fails(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios.jsonl"
    write_jsonl(scenarios, [SAYS])
    code = main(
        [
            "eval",
            "agent",
            "score",
            "--scenarios",
            str(scenarios),
            "--results-dir",
            str(tmp_path),
            "--systems",
            "agent",
        ]
    )
    assert code == 2
