"""`sec-agent golden pool|label|qrels` over a simulated filing indexed in Postgres."""

import datetime as dt
import io
from pathlib import Path

import psycopg
import pytest
from golden_data import GOLDEN_FIXTURES, split_company

from sec_agent.cli import main
from sec_agent.filings.index_version import ChunkConfig
from sec_agent.filings.models import FilingRef
from sec_agent.filings.pipeline import index_filing
from sec_agent.filings.store import PostgresChunkStore, apply_schema
from sec_agent.golden.gret.chunks import PostgresChunkText
from sec_agent.golden.gret.models import ChunkRef, Label, PoolItem
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import CompanySplit, write_split

ACC = "9999999999-25-000008"
SIM_10K = Path(__file__).resolve().parents[1] / "fixtures" / "filings" / "sim-10k.htm"


@pytest.fixture
def indexed_db(db_url: str) -> tuple[str, str]:
    """The simulated 10-K indexed with 30-token chunks, alone in the chunk tables."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE indexed_filings CASCADE")
    chunk_db = db_url
    filing_10k = FilingRef(
        cik="9999999999",
        accession=ACC,
        form="10-K",
        filing_date=dt.date(2025, 2, 20),
        report_date=dt.date(2024, 12, 31),
        primary_document="simw-20241231.htm",
    )
    indexed = index_filing(SIM_10K.read_bytes(), filing_10k, ChunkConfig(max_tokens=30))
    with PostgresChunkStore.connect(chunk_db) as store:
        store.replace(indexed)
    return chunk_db, indexed.index_version


@pytest.fixture
def split_file(tmp_path: Path) -> Path:
    split = CompanySplit(
        seed=1,
        universe_sha256="0" * 64,
        companies=(split_company("SIMW", 9999999999, "test", name="Simulated Widgets Inc."),),
    )
    path = tmp_path / "split.json"
    write_split(path, split)
    return path


def test_chunk_text_source_returns_text_and_hash(indexed_db: tuple[str, str]) -> None:
    url, version = indexed_db
    refs = [ChunkRef(accession=ACC, section="mdna", ordinal=0)]
    with PostgresChunkText.connect(url) as source:
        texts = source.fetch(index_version=version, refs=refs)
        assert set(texts) == set(refs)
        assert texts[refs[0]].cik == "9999999999"
        assert len(texts[refs[0]].text_sha256) == 64
        assert source.fetch(index_version="other", refs=refs) == {}


def _pool(url: str, version: str, split_file: Path, out: Path, *systems: str) -> list[str]:
    args = ["golden", "pool", "--database-url", url, "--index-version", version]
    args += ["--questions", str(GOLDEN_FIXTURES / "g_ret_questions.sim.jsonl")]
    args += ["--split-file", str(split_file), "--out", str(out), "--seed", "4"]
    for system in systems:
        args += ["--run", str(GOLDEN_FIXTURES / f"{system}.sim.run")]
    return args


def test_pool_label_and_qrels_end_to_end(
    indexed_db: tuple[str, str],
    split_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, version = indexed_db
    pool_file, labels_file, qrels_file = (tmp_path / n for n in ("pool.jsonl", "l.jsonl", "q"))
    assert main(_pool(url, version, split_file, pool_file, "bm25", "vector", "hybrid")) == 0
    assert "pooled 9 chunks for 2 questions from 3 systems (bm25, hybrid, vector)" in (
        capsys.readouterr().out
    )
    pool = read_jsonl(pool_file, PoolItem)
    assert len(pool) == 9
    assert all(item.text for item in pool)

    label = ["golden", "label", "--pool", str(pool_file), "--labels", str(labels_file)]
    label += ["--questions", str(GOLDEN_FIXTURES / "g_ret_questions.sim.jsonl")]
    label += ["--split-file", str(split_file)]
    monkeypatch.setattr("sys.stdin", io.StringIO("2\n0\nq\n"))
    assert main(label) == 0
    assert "labelled 2, skipped 0, 7 pending" in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO("1\n"))
    assert main(label) == 0  # resumes at the first pending chunk
    assert "labelled 1, skipped 0, 6 pending" in capsys.readouterr().out
    labels = read_jsonl(labels_file, Label)
    assert [lbl.grade for lbl in labels] == [2, 0, 1]
    assert [lbl.docid for lbl in labels] == [item.docid for item in pool[:3]]

    qrels = ["golden", "qrels", "--pool", str(pool_file), "--labels", str(labels_file)]
    assert main([*qrels, "--out", str(qrels_file)]) == 0
    assert "3 labelled, 6 pending" in capsys.readouterr().out
    assert qrels_file.read_text("utf-8").splitlines() == [
        f"{item.qid} 0 {item.docid} {grade}"
        for item, grade in zip(pool[:3], (2, 0, 1), strict=True)
    ]


def test_pool_warns_when_fewer_than_three_systems_are_pooled(
    indexed_db: tuple[str, str],
    split_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, version = indexed_db
    assert main(_pool(url, version, split_file, tmp_path / "p.jsonl", "bm25")) == 0
    assert "warning: the plan pools 3 systems" in capsys.readouterr().err


def test_pool_fails_when_a_chunk_is_not_in_the_index(
    indexed_db: tuple[str, str],
    split_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, _ = indexed_db
    assert main(_pool(url, "chunks-other", split_file, tmp_path / "p.jsonl", "bm25")) == 2
    assert "missing" in capsys.readouterr().err
    assert not (tmp_path / "p.jsonl").exists()


def test_pool_extend_keeps_labelled_items_and_adds_new_ones_as_pending(
    indexed_db: tuple[str, str],
    split_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, version = indexed_db
    pool_file, labels_file = tmp_path / "pool.jsonl", tmp_path / "labels.jsonl"
    assert main(_pool(url, version, split_file, pool_file, "bm25")) == 0
    first = read_jsonl(pool_file, PoolItem)
    label = ["golden", "label", "--pool", str(pool_file), "--labels", str(labels_file)]
    label += ["--questions", str(GOLDEN_FIXTURES / "g_ret_questions.sim.jsonl")]
    label += ["--split-file", str(split_file)]
    monkeypatch.setattr("sys.stdin", io.StringIO("2\n0\nq\n"))
    assert main(label) == 0
    capsys.readouterr()

    extend = _pool(url, version, split_file, pool_file, "bm25", "vector", "hybrid")
    assert main([*extend, "--extend", str(pool_file)]) == 0
    out = capsys.readouterr().out
    extended = read_jsonl(pool_file, PoolItem)
    assert len(extended) == 9
    assert {i.docid for i in first} <= {i.docid for i in extended}
    assert f"kept {len(first)} previously pooled chunks, added {9 - len(first)} new" in out
    assert f"dropped 0 no longer in {version}" in out

    qrels = ["golden", "qrels", "--pool", str(pool_file), "--labels", str(labels_file)]
    assert main([*qrels, "--out", str(tmp_path / "q")]) == 0
    assert "2 labelled, 7 pending" in capsys.readouterr().out


def test_pool_extend_needs_an_existing_pool_file(
    indexed_db: tuple[str, str],
    split_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, version = indexed_db
    args = _pool(url, version, split_file, tmp_path / "p.jsonl", "bm25")
    assert main([*args, "--extend", str(tmp_path / "missing.jsonl")]) == 2
    assert "missing.jsonl" in capsys.readouterr().err
