"""`sec-agent traces table`: the L1 table from a span file, and its rows in runs.csv.

The spans are hand-built (simulated timings), not measured.
"""

from pathlib import Path

import pytest
from span_records import turn_trace

from sec_agent.cli import main
from sec_agent.runs import read_runs


def _span_file(tmp_path: Path) -> Path:
    path = tmp_path / "spans.jsonl"
    records = [
        *turn_trace(1, turn_ms=100, llm_ms=(60,), tool_ms=(10,), tokens=((100, 10),)),
        *turn_trace(2, turn_ms=200, llm_ms=(150,), tool_ms=(20,), tokens=((200, 20),)),
    ]
    path.write_text("".join(r.model_dump_json() + "\n" for r in records), "utf-8")
    return path


def test_the_table_prints_latency_per_step_and_tokens_per_question(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["traces", "table", str(_span_file(tmp_path))]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].split() == ["step", "n", "errors", "p50_ms", "p95_ms"]
    assert out[1].split() == ["turn", "2", "0", "150.0", "195.0"]
    assert any(line.split()[:2] == ["tool:get_fact", "2"] for line in out)
    tokens_header = out.index(next(line for line in out if line.startswith("tokens")))
    assert out[tokens_header].split() == ["tokens", "questions", "mean", "p50", "p95"]
    assert out[tokens_header + 3].split() == ["total", "2", "165.0", "165.0", "214.5"]


def test_record_appends_the_rows_to_runs_csv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = tmp_path / "runs.csv"
    code = main(
        [
            "traces",
            "table",
            str(_span_file(tmp_path)),
            "--record",
            str(runs),
            "--git-sha",
            "abc1234",
            "--system",
            "b2",
            "--split",
            "dev",
            "--cohort",
            "simulated",
            "--notes",
            "simulated users",
        ]
    )
    assert code == 0
    rows = read_runs(runs)
    assert {r.cohort for r in rows} == {"simulated"}
    by_metric = {r.metric: r for r in rows}
    assert by_metric["L1.latency_p50.turn"].value == 150.0
    assert by_metric["L1.tokens_per_question_mean.total"].value == 165.0
    assert f"recorded {len(rows)} rows" in capsys.readouterr().out


def test_record_needs_the_system_split_and_cohort(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = tmp_path / "runs.csv"
    args = ["traces", "table", str(_span_file(tmp_path)), "--record", str(runs)]
    assert main([*args, "--git-sha", "abc1234"]) == 2
    assert "--system, --split and --cohort" in capsys.readouterr().err
    assert not runs.exists()


def test_an_unreadable_span_file_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text("{oops\n", "utf-8")
    assert main(["traces", "table", str(path)]) == 2
    assert "line 1" in capsys.readouterr().err


def test_a_span_file_without_turns_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text("", "utf-8")
    assert main(["traces", "table", str(path)]) == 2
    assert "no sec-agent span" in capsys.readouterr().err
