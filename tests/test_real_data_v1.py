"""Committed derivations of the real-data build v1: retrieval runs, the G-ret pool, a data note.

The database and raw filings are never committed; these small files are what later tasks
(labelling, R1 scoring) read, so they must agree with one another and with the questions.
"""

from pathlib import Path

from sec_agent.golden.gret.models import PoolItem
from sec_agent.golden.gret.questions import load_questions
from sec_agent.golden.gret.trec import parse_run
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import read_split
from sec_agent.retrieval.snapshot import read_manifest

SYSTEMS = ("bm25", "vector", "hybrid")
POOL_DEPTH = 20


def _paths(repo_root: Path) -> tuple[Path, Path, Path]:
    golden = repo_root / "data" / "golden"
    return (
        golden,
        repo_root / "results" / "retrieval" / "v1",
        repo_root / "data" / "real_data_v1.md",
    )


def _question_ids(repo_root: Path) -> set[str]:
    golden, _, _ = _paths(repo_root)
    split = read_split(golden / "company_split.json")
    return {q.id for q in load_questions(golden / "g_ret_questions.jsonl", split)}


def test_runs_pin_snapshot_v1_and_cover_every_question(repo_root: Path) -> None:
    _, runs, _ = _paths(repo_root)
    snapshot = read_manifest(runs / "snapshot.json")
    assert snapshot.name == "v1"
    assert snapshot.chunk_count > 0
    assert snapshot.filing_count > 0
    questions = _question_ids(repo_root)
    for system in SYSTEMS:
        hits = parse_run((runs / f"{system}.run").read_text("utf-8"))
        assert {h.system for h in hits} == {system}
        assert {h.qid for h in hits} == questions, system


def test_pool_is_the_top_20_of_the_three_runs_at_the_snapshot_index(repo_root: Path) -> None:
    golden, runs, _ = _paths(repo_root)
    snapshot = read_manifest(runs / "snapshot.json")
    pool = read_jsonl(golden / "g_ret_pool.jsonl", PoolItem)
    assert {item.index_version for item in pool} == {snapshot.index_version}
    assert {item.qid for item in pool} == _question_ids(repo_root)
    assert {s for item in pool for s in item.systems} == set(SYSTEMS)
    top = {
        (h.qid, h.chunk.docid)
        for system in SYSTEMS
        for h in parse_run((runs / f"{system}.run").read_text("utf-8"))
        if h.rank <= POOL_DEPTH
    }
    assert {(item.qid, item.docid) for item in pool} == top


def test_data_note_states_the_counts_of_the_committed_files(repo_root: Path) -> None:
    golden, runs, note_path = _paths(repo_root)
    snapshot = read_manifest(runs / "snapshot.json")
    pool = read_jsonl(golden / "g_ret_pool.jsonl", PoolItem)
    note = note_path.read_text("utf-8")
    assert snapshot.index_version in note
    assert snapshot.content_sha256 in note
    for count in (snapshot.chunk_count, snapshot.filing_count, len(pool)):
        assert f"| {count:,} |" in note or f"| {count} |" in note, count
