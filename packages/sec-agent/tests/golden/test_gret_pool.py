"""G-ret: questions on test companies only, TREC runs, top-k pooling with blind order."""

import datetime as dt
from pathlib import Path

import pytest
from golden_data import GOLDEN_FIXTURES, split_company

from sec_agent.golden.gret.models import ChunkRef, ChunkText, RetQuestion, RunHit
from sec_agent.golden.gret.pool import attach_text, build_pool
from sec_agent.golden.gret.questions import load_questions
from sec_agent.golden.gret.trec import parse_run
from sec_agent.golden.split import CompanySplit

ACC = "9999999999-25-000008"


@pytest.fixture
def sim_split() -> CompanySplit:
    return CompanySplit(
        seed=1,
        universe_sha256="0" * 64,
        companies=(
            split_company("SIMW", 9999999999, "test", name="Simulated Widgets Inc."),
            split_company("SIMT", 9999999998, "train"),
        ),
    )


@pytest.fixture
def questions(sim_split: CompanySplit) -> list[RetQuestion]:
    return load_questions(GOLDEN_FIXTURES / "g_ret_questions.sim.jsonl", sim_split)


def _runs() -> list[str]:
    return [
        (GOLDEN_FIXTURES / f"{s}.sim.run").read_text("utf-8") for s in ("bm25", "vector", "hybrid")
    ]


def _hits() -> list[RunHit]:
    return [hit for text in _runs() for hit in parse_run(text)]


def test_questions_load_with_their_test_company(questions: list[RetQuestion]) -> None:
    assert [q.id for q in questions] == ["q-001", "q-002"]
    assert questions[0].ticker == "SIMW"
    assert questions[0].written_on == dt.date(2026, 11, 13)


def _write(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "q.jsonl"
    path.write_text("".join(f"{line}\n" for line in lines), "utf-8")
    return path


def test_a_question_on_a_company_outside_the_test_split_is_refused(
    tmp_path: Path, sim_split: CompanySplit
) -> None:
    path = _write(
        tmp_path,
        '{"id": "q-9", "ticker": "SIMT", "question": "Why?", "written_on": "2026-11-13"}',
    )
    with pytest.raises(ValueError, match="test split"):
        load_questions(path, sim_split)


def test_duplicate_question_ids_are_refused(tmp_path: Path, sim_split: CompanySplit) -> None:
    line = '{"id": "q-1", "ticker": "SIMW", "question": "Why?", "written_on": "2026-11-13"}'
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(_write(tmp_path, line, line), sim_split)


def test_chunk_ref_round_trips_its_docid() -> None:
    ref = ChunkRef.parse(f"{ACC}/risk_factors/2")
    assert ref == ChunkRef(accession=ACC, section="risk_factors", ordinal=2)
    assert ref.docid == f"{ACC}/risk_factors/2"
    with pytest.raises(ValueError, match="docid"):
        ChunkRef.parse(f"{ACC}/exhibits/2")


def test_parse_run_reads_trec_lines() -> None:
    hits = parse_run(_runs()[0])
    assert len(hits) == 5
    first = hits[0]
    assert (first.qid, first.rank, first.score, first.system) == ("q-001", 1, 12.5, "bm25")
    assert first.chunk == ChunkRef(accession=ACC, section="risk_factors", ordinal=0)


@pytest.mark.parametrize(
    "line",
    [
        f"q-001 Q0 {ACC}/mdna/0 1 0.5",  # five fields
        f"q-001 Q1 {ACC}/mdna/0 1 0.5 bm25",  # not Q0
        f"q-001 Q0 {ACC}/mdna/0 zero 0.5 bm25",  # rank not a number
        f"q-001 Q0 {ACC}/mdna/0 0 0.5 bm25",  # rank starts at 1
        "q-001 Q0 not-a-docid 1 0.5 bm25",
    ],
)
def test_parse_run_names_the_bad_line(line: str) -> None:
    with pytest.raises(ValueError, match="line 2"):
        parse_run(f"q-001 Q0 {ACC}/mdna/1 1 0.5 bm25\n{line}\n")


def test_pool_is_the_union_of_each_systems_top_k(questions: list[RetQuestion]) -> None:
    pool = build_pool(questions, _hits(), depth=2, seed=5)
    by_question: dict[str, set[str]] = {}
    for entry in pool:
        by_question.setdefault(entry.qid, set()).add(entry.chunk.docid)
    assert by_question == {
        "q-001": {f"{ACC}/risk_factors/{n}" for n in (0, 1, 2)},
        "q-002": {f"{ACC}/mdna/0", f"{ACC}/mdna/1", f"{ACC}/market_risk/0", f"{ACC}/business/3"},
    }


def test_pool_records_which_systems_found_each_chunk_and_its_best_rank(
    questions: list[RetQuestion],
) -> None:
    pool = build_pool(questions, _hits(), depth=20, seed=5)
    entry = next(e for e in pool if e.qid == "q-001" and e.chunk.docid == f"{ACC}/risk_factors/1")
    assert entry.systems == ("bm25", "vector")
    assert entry.best_rank == 1
    assert len([e for e in pool if e.qid == "q-001"]) == 5


def test_pool_order_is_seeded_and_does_not_follow_any_system(
    questions: list[RetQuestion],
) -> None:
    one = build_pool(questions, _hits(), depth=20, seed=5)
    assert one == build_pool(questions, list(reversed(_hits())), depth=20, seed=5)
    assert [e.qid for e in one] == ["q-001"] * 5 + ["q-002"] * 4  # question order kept
    orders = {
        tuple(e.chunk.docid for e in build_pool(questions, _hits(), depth=20, seed=s))
        for s in range(8)
    }
    assert len(orders) > 1


def test_pool_refuses_hits_for_unknown_questions(questions: list[RetQuestion]) -> None:
    hits = parse_run(f"q-404 Q0 {ACC}/mdna/0 1 1.0 bm25\n")
    with pytest.raises(ValueError, match="q-404"):
        build_pool(questions, hits, depth=20, seed=1)


def test_attach_text_adds_the_chunk_text_and_its_hash(questions: list[RetQuestion]) -> None:
    first = [h for h in _hits() if h.qid == "q-001"]
    pool = build_pool(questions[:1], first, depth=1, seed=1)
    texts = {
        e.chunk: ChunkText(cik="9999999999", text=f"text of {e.chunk.docid}", text_sha256="a" * 64)
        for e in pool
    }
    items = attach_text(pool, texts, questions[:1], index_version="v1")
    assert [i.docid for i in items] == [e.chunk.docid for e in pool]
    assert all(i.index_version == "v1" and i.ticker == "SIMW" for i in items)
    assert items[0].text == f"text of {items[0].docid}"
    with pytest.raises(ValueError, match="missing"):
        attach_text(pool, {}, questions[:1], index_version="v1")
