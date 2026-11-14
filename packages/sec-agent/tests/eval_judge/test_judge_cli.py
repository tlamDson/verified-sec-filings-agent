"""`sec-agent eval judge sample|score` over files (no database, no model)."""

from pathlib import Path

import pytest
from judge_kit import question, record, reply, scenario, transcript

from sec_agent.cli import main
from sec_agent.eval.judge.models import BlindItem, KeyEntry, Label, Verdict
from sec_agent.golden.jsonl import read_jsonl, write_jsonl
from sec_agent.runs import read_runs


def committed_results(tmp_path: Path) -> list[str]:
    right, late = question("revenue"), question("cash")
    write_jsonl(tmp_path / "g_num.jsonl", [right, late])
    numeric = tmp_path / "numeric"
    write_jsonl(numeric / "b0.jsonl", [record(right, "b0", reply("1000"))])
    write_jsonl(
        numeric / "b1.jsonl",
        [record(late, "b1", reply("1000", fiscal_year=2023, period_end="2023-01-29"))],
    )
    write_jsonl(tmp_path / "scenarios.jsonl", [scenario("a1-002", cite=True)])
    agent = tmp_path / "agent"
    text = "SIMW makes widgets. This is not investment advice."
    write_jsonl(agent / "rag.jsonl", [transcript("a1-002", "rag", text)])
    return [
        "--questions", str(tmp_path / "g_num.jsonl"),
        "--numeric-dir", str(numeric),
        "--numeric-systems", "b0,b1",
        "--scenarios", str(tmp_path / "scenarios.jsonl"),
        "--agent-dir", str(agent),
        "--agent-systems", "rag",
    ]  # fmt: skip


def test_sample_writes_blind_items_and_a_separate_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "judge"
    args = ["eval", "judge", "sample", *committed_results(tmp_path), "--out", str(out)]
    assert main([*args, "--total", "10", "--seed", "3"]) == 0
    items = read_jsonl(out / "items.jsonl", BlindItem)
    key = read_jsonl(out / "key.jsonl", KeyEntry)
    assert len(items) == len(key) == 3
    assert {k.stratum for k in key} == {"correct", "wrong_period", "citation"}
    printed = capsys.readouterr().out
    assert "citation" in printed
    assert "3 items" in printed


def test_score_prints_each_judge_and_records_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "judge"
    assert main(["eval", "judge", "sample", *committed_results(tmp_path), "--out", str(out)]) == 0
    key = read_jsonl(out / "key.jsonl", KeyEntry)
    labels = tmp_path / "labels.jsonl"
    write_jsonl(labels, [Label(id=k.id, label=k.grader_verdict, rater="sim-rater") for k in key])
    verdicts = tmp_path / "sim-judge.jsonl"
    write_jsonl(verdicts, [Verdict(id=k.id, verdict="correct", judge="sim-judge") for k in key])
    runs = tmp_path / "runs.csv"
    code = main(
        [
            "eval", "judge", "score",
            "--dir", str(out),
            "--labels", str(labels),
            "--labelled-by", "simulated raters (test)",
            "--verdicts", str(verdicts),
            "--record", str(runs),
            "--git-sha", "abc123",
        ]
    )  # fmt: skip
    assert code == 0
    printed = capsys.readouterr().out
    assert "grader" in printed
    assert "sim-judge" in printed
    rows = read_runs(runs)
    assert {r.system for r in rows} == {"grader", "sim-judge"}
    assert {r.metric for r in rows} == {"J1_kappa", "J1_tpr", "J1_tnr"}


def test_score_without_labels_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "judge"
    assert main(["eval", "judge", "sample", *committed_results(tmp_path), "--out", str(out)]) == 0
    code = main(["eval", "judge", "score", "--dir", str(out), "--labels", str(tmp_path / "no")])
    assert code == 2
    assert "no labels" in capsys.readouterr().err
