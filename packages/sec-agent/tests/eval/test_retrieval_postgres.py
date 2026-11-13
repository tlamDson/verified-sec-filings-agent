"""Retrieval baselines over the indexed simulated corpus, and `sec-agent eval retrieval run`."""

import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from eval_data import number_question
from golden_data import split_company
from retrieval_corpus import CIK_A, CONFIG, VERSION, store_corpus
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.cli import main
from sec_agent.eval.numeric.passages import SearchPassages
from sec_agent.eval.retrieval.postgres import CompanyChunks, random_ranker, search_ranker
from sec_agent.golden.gret.models import RetQuestion
from sec_agent.golden.gret.trec import parse_run
from sec_agent.golden.jsonl import write_jsonl
from sec_agent.golden.split import CompanySplit, write_split
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.schema import apply_schema
from sec_agent.retrieval.snapshot import create_snapshot
from sec_agent.retrieval.space import make_space

Conn = psycopg.Connection[Any]
QUESTION = RetQuestion(
    id="q-001", ticker="SIMW", question="supplier risk", written_on=dt.date(2026, 1, 1)
)


def _fake_embedder(spec: EmbedderSpec, device: str | None) -> HashEmbedder:
    return HashEmbedder(spec)


@pytest.fixture
def built_db(db_url: str) -> str:
    """The retrieval corpus stored under VERSION and embedded with the hash embedder."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute(
            "TRUNCATE indexed_filings, embedding_spaces, lexical_stats, lexical_df CASCADE"
        )
    store_corpus(db_url, CONFIG)
    with psycopg.connect(db_url, autocommit=True) as conn:
        build_index(conn, VERSION, HashEmbedder())
    return db_url


@pytest.fixture
def conn(built_db: str) -> Iterator[Conn]:
    with psycopg.connect(built_db, autocommit=True) as connection:
        yield connection


def _accessions(conn: Conn, cik: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT accession FROM chunks WHERE index_version = %s AND cik = %s",
        (VERSION, cik),
    ).fetchall()
    return {str(r[0]) for r in rows}


@pytest.mark.parametrize("mode", ["lexical", "dense", "hybrid"])
def test_search_ranker_keeps_to_the_question_company(conn: Conn, mode: str) -> None:
    space = make_space(VERSION, HASH_SPEC)
    ranker = search_ranker(conn, space, HashEmbedder(), mode)  # pyright: ignore[reportArgumentType]
    ranked = ranker(QUESTION, CIK_A, 5)
    assert 0 < len(ranked) <= 5
    assert {ref.accession for ref, _ in ranked} <= _accessions(conn, CIK_A)


def test_random_ranker_is_seeded_and_company_only(conn: Conn) -> None:
    chunks = CompanyChunks(conn, VERSION)
    first = random_ranker(chunks, seed=3)(QUESTION, CIK_A, 6)
    assert first == random_ranker(chunks, seed=3)(QUESTION, CIK_A, 6)
    assert first != random_ranker(chunks, seed=4)(QUESTION, CIK_A, 6)
    assert len(first) == 6
    assert {ref.accession for ref, _ in first} <= _accessions(conn, CIK_A)


def test_eval_retrieval_run_writes_one_run_per_system(
    conn: Conn,
    built_db: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create_snapshot(conn, "eval-1", make_space(VERSION, HASH_SPEC))
    monkeypatch.setattr("sec_agent.eval.retrieval_cli.query_embedder", _fake_embedder)
    split = CompanySplit(
        seed=1, universe_sha256="0" * 64, companies=(split_company("SIMW", int(CIK_A), "test"),)
    )
    write_split(tmp_path / "split.json", split)
    write_jsonl(tmp_path / "q.jsonl", [QUESTION])
    out = tmp_path / "runs"
    args = ["eval", "retrieval", "run", "--database-url", built_db, "--snapshot", "eval-1"]
    args += ["--questions", str(tmp_path / "q.jsonl"), "--split-file", str(tmp_path / "split.json")]
    args += ["--depth", "4", "--out-dir", str(out)]
    assert main(args) == 0
    printed = capsys.readouterr().out
    assert "snapshot eval-1 verified before and after" in printed
    for system in ("random", "bm25", "vector", "hybrid"):
        hits = parse_run((out / f"{system}.run").read_text("utf-8"))
        assert {h.system for h in hits} == {system}
        assert [h.rank for h in hits] == [1, 2, 3, 4]
    assert (out / "snapshot.json").exists()


def test_eval_retrieval_run_refuses_an_unknown_snapshot(
    built_db: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["eval", "retrieval", "run", "--database-url", built_db, "--snapshot", "nope"]
    args += ["--out-dir", str(tmp_path)]
    assert main(args) == 1
    assert "nope" in capsys.readouterr().err


def test_b1_passages_come_from_the_question_companies(conn: Conn) -> None:
    question = number_question("revenue", "1")  # about SIMW, CIK_A
    source = SearchPassages(conn, make_space(VERSION, HASH_SPEC), HashEmbedder())
    passages = source.passages(question, 3)
    assert 0 < len(passages) <= 3
    assert {p.docid.split("/")[0] for p in passages} <= _accessions(conn, CIK_A)
    assert all(p.text for p in passages)
