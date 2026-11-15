"""Committed derivations of build v2 (Exhibit 13, index parser 2) sit beside v1, not over it."""

from pathlib import Path

from sec_agent.golden.gret.labels import qrels_lines
from sec_agent.golden.gret.models import Label, PoolItem
from sec_agent.golden.gret.trec import parse_run, qrels_text
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.retrieval.snapshot import read_manifest

SYSTEMS = ("bm25", "vector", "hybrid")


def test_v2_pool_extends_the_v1_pool_at_the_v2_index(repo_root: Path) -> None:
    golden = repo_root / "data" / "golden"
    snapshot = read_manifest(repo_root / "results" / "retrieval" / "v2" / "snapshot.json")
    v1 = read_jsonl(golden / "g_ret_pool.jsonl", PoolItem)
    v2 = read_jsonl(golden / "g_ret_pool_v2.jsonl", PoolItem)
    assert {item.index_version for item in v2} == {snapshot.index_version}
    assert {item.index_version for item in v1} != {snapshot.index_version}
    assert {(i.qid, i.docid) for i in v1} <= {(i.qid, i.docid) for i in v2}
    top: set[tuple[str, str]] = set()
    for system in SYSTEMS:
        text = (repo_root / "results" / "retrieval" / "v2" / f"{system}.run").read_text("utf-8")
        hits = [h for h in parse_run(text) if h.rank <= 20]
        top |= {(h.qid, h.chunk.docid) for h in hits}
    assert top <= {(i.qid, i.docid) for i in v2}


def test_each_qrels_file_is_its_pool_with_the_shared_labels(repo_root: Path) -> None:
    golden = repo_root / "data" / "golden"
    labels = read_jsonl(golden / "g_ret_labels.jsonl", Label)
    for pool, qrels in (
        ("g_ret_pool.jsonl", "g_ret.qrels"),
        ("g_ret_pool_v2.jsonl", "g_ret_v2.qrels"),
    ):
        items = read_jsonl(golden / pool, PoolItem)
        assert (golden / qrels).read_text("utf-8") == qrels_text(qrels_lines(items, labels))
