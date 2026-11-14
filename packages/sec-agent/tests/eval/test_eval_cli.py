"""`sec-agent eval numeric` and `sec-agent eval retrieval score` over files (no database)."""

import datetime as dt
from pathlib import Path

import pytest
from eval_data import number_question, peer_question
from golden_data import split_company

from sec_agent.cli import main
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.golden.gret.models import RetQuestion
from sec_agent.golden.jsonl import write_jsonl
from sec_agent.golden.split import CompanySplit, write_split
from sec_agent.runs import read_runs

T0 = dt.datetime(2026, 11, 13, tzinfo=dt.UTC)
REVENUE = number_question("revenue", "100")
PEER = peer_question("revenue")
DEV = number_question("dev_only", "5").model_copy(update={"split": "dev"})
RIGHT = (
    '{"answer": "number", "value": 100, "unit": "USD", "fiscal_year": 2024, "fiscal_period": "FY"}'
)


def _records(system: str, revenue: str, peer: str) -> list[AnswerRecord]:
    return [
        AnswerRecord(
            qid=q.id,
            system=system,
            model="fake-1",
            prompt_sha256="0" * 64,
            output=out,
            answered_at=T0,
        )
        for q, out in ((REVENUE, revenue), (PEER, peer))
    ]


@pytest.fixture
def numeric_files(tmp_path: Path) -> tuple[Path, Path]:
    questions = tmp_path / "g_num.jsonl"
    write_jsonl(questions, [REVENUE, PEER, DEV])
    results = tmp_path / "results"
    write_jsonl(results / "b0.jsonl", _records("b0", "no idea", '{"answer": "not_found"}'))
    write_jsonl(
        results / "b1.jsonl", _records("b1", RIGHT, '{"answer": "company", "ticker": "SIMB"}')
    )
    return questions, results


def _numeric(questions: Path, results: Path, *extra: str) -> list[str]:
    args = ["eval", "numeric", "--questions", str(questions), "--split", "test"]
    return [*args, "--systems", "b0,b1", "--results-dir", str(results), *extra]


def test_eval_numeric_prints_accuracy_and_mcnemar(
    numeric_files: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_numeric(*numeric_files)) == 0
    out = capsys.readouterr().out
    assert "N1 numeric accuracy, split test: 2 of 2 questions scored (index v-test)" in out
    for line in ("b0  0/2  0.000", "b1  2/2  1.000"):
        assert line in out
    assert "unparsed 1, not_found 1" in out
    assert "b1 vs b0: b1 only 2, b0 only 0, exact McNemar p = 0.5000" in out


def test_eval_numeric_records_rows_in_runs_csv(
    numeric_files: tuple[Path, Path], tmp_path: Path
) -> None:
    runs = tmp_path / "runs.csv"
    assert main(_numeric(*numeric_files, "--record", str(runs), "--git-sha", "abc1234")) == 0
    rows = read_runs(runs)
    assert [(r.metric, r.system, r.n, r.value) for r in rows] == [
        ("N1", "b0", 2, 0.0),
        ("N1", "b1", 2, 1.0),
        ("N1_mcnemar_p", "b1_vs_b0", 2, 0.5),
    ]
    first = rows[0]
    assert (first.split, first.cohort, first.git_sha, first.index_version) == (
        "test",
        "none",
        "abc1234",
        "v-test",
    )
    assert first.ci_low == 0.0
    assert first.ci_high is not None
    assert "fake-1" in first.notes


def test_eval_numeric_needs_every_results_file(
    numeric_files: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    questions, results = numeric_files
    args = ["eval", "numeric", "--questions", str(questions), "--split", "test"]
    assert main([*args, "--systems", "b0,b2", "--results-dir", str(results)]) == 2
    assert "b2.jsonl" in capsys.readouterr().err


ACC = "9999999999-25-000008"


@pytest.fixture
def retrieval_files(tmp_path: Path) -> dict[str, Path]:
    split = CompanySplit(
        seed=1,
        universe_sha256="0" * 64,
        companies=(
            split_company("SIMW", 9999999999, "test"),
            split_company("SIMB", 9999999998, "test"),
        ),
    )
    write_split(tmp_path / "split.json", split)
    write_jsonl(
        tmp_path / "q.jsonl",
        [
            RetQuestion(id=qid, ticker=t, question="q", written_on=dt.date(2026, 1, 1))
            for qid, t in (("q1", "SIMW"), ("q2", "SIMB"))
        ],
    )
    (tmp_path / "g.qrels").write_text(f"q1 0 {ACC}/mdna/0 2\nq2 0 {ACC}/mdna/1 1\n", "utf-8")
    (tmp_path / "bm25.run").write_text(
        f"q1 Q0 {ACC}/mdna/0 1 2.0 bm25\nq2 Q0 {ACC}/mdna/9 1 2.0 bm25\n", "utf-8"
    )
    (tmp_path / "hybrid.run").write_text(
        f"q1 Q0 {ACC}/mdna/0 1 0.1 hybrid\nq2 Q0 {ACC}/mdna/1 1 0.1 hybrid\n", "utf-8"
    )
    return {
        "split": tmp_path / "split.json",
        "questions": tmp_path / "q.jsonl",
        "qrels": tmp_path / "g.qrels",
        "bm25": tmp_path / "bm25.run",
        "hybrid": tmp_path / "hybrid.run",
    }


def _score(files: dict[str, Path], *extra: str) -> list[str]:
    args = ["eval", "retrieval", "score", "--qrels", str(files["qrels"])]
    args += ["--questions", str(files["questions"]), "--split-file", str(files["split"])]
    args += ["--run", str(files["bm25"]), "--run", str(files["hybrid"])]
    return [*args, "--resamples", "200", *extra]


def test_eval_retrieval_score_prints_metrics_and_comparisons(
    retrieval_files: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_score(retrieval_files, "--baseline", "bm25", "--oracle")) == 0
    out = capsys.readouterr().out
    assert "R1 retrieval: 2 of 2 questions scored, 2 companies" in out
    for system in ("recall@5", "ndcg@10", "mrr@10", "bm25", "hybrid", "oracle"):
        assert system in out
    assert "hybrid - bm25" in out


def test_eval_retrieval_score_records_rows(
    retrieval_files: dict[str, Path], tmp_path: Path
) -> None:
    runs = tmp_path / "runs.csv"
    extra = ["--baseline", "bm25", "--record", str(runs), "--git-sha", "abc1234"]
    assert main(_score(retrieval_files, *extra, "--index-version", "v-test")) == 0
    rows = read_runs(runs)
    metrics = [(r.metric, r.system) for r in rows]
    assert ("R1_recall@5", "bm25") in metrics
    assert ("R1_mrr@10", "hybrid") in metrics
    assert ("R1_ndcg@10_diff", "hybrid_vs_bm25") in metrics
    hybrid = next(r for r in rows if r.metric == "R1_recall@5" and r.system == "hybrid")
    assert (hybrid.value, hybrid.n, hybrid.split, hybrid.index_version) == (
        1.0,
        2,
        "test",
        "v-test",
    )


def test_eval_retrieval_score_can_record_only_the_comparisons(
    retrieval_files: dict[str, Path], tmp_path: Path
) -> None:
    """A second baseline adds its paired differences without repeating the systems' rows."""
    runs = tmp_path / "runs.csv"
    extra = ["--baseline", "bm25", "--record", str(runs), "--git-sha", "abc1234"]
    assert main(_score(retrieval_files, *extra, "--comparisons-only")) == 0
    rows = read_runs(runs)
    assert rows
    assert {r.system for r in rows} == {"hybrid_vs_bm25"}


def test_comparisons_only_needs_a_baseline(retrieval_files: dict[str, Path], tmp_path: Path) -> None:
    extra = ["--record", str(tmp_path / "runs.csv"), "--comparisons-only"]
    assert main(_score(retrieval_files, *extra)) == 2


def test_eval_retrieval_score_refuses_a_bad_run_file(
    retrieval_files: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    retrieval_files["bm25"].write_text("q1 Q0 nonsense 1 1.0 bm25\n", "utf-8")
    assert main(_score(retrieval_files)) == 2
    assert "bm25.run" in capsys.readouterr().err
