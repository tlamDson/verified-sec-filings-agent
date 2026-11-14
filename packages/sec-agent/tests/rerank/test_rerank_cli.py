"""`sec-agent rerank run|bench`: ONNX reranker over a base run's top chunks, from files only."""

import csv
import datetime as dt
import json
from pathlib import Path

import pytest
from rerank_kit import sha256_of, tiny_score, write_tiny_model

from sec_agent.cli import main
from sec_agent.golden.gret.models import ChunkRef, PoolItem, RunHit
from sec_agent.golden.gret.trec import parse_run, run_text
from sec_agent.rerank.models import MANIFEST_FILE, RerankerManifest

SPLIT_FILE = Path(__file__).resolve().parents[4] / "data" / "golden" / "company_split.json"
TEXTS = ["revenue rose", "the oil price fell the the", "supplier risk"]
QUESTION = "oil price risk"


def _ref(n: int) -> ChunkRef:
    return ChunkRef(accession="0000000001-24-000001", section="mdna", ordinal=n)


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps({"id": "q1", "ticker": "COP", "question": QUESTION, "written_on": "2026-11-13"})
        + "\n",
        "utf-8",
    )
    pool = tmp_path / "pool.jsonl"
    items = [
        PoolItem(
            qid="q1",
            chunk=_ref(n),
            systems=("hybrid",),
            best_rank=n + 1,
            ticker="COP",
            index_version="v-test",
            text=text,
            text_sha256=f"{n:064x}",
        )
        for n, text in enumerate(TEXTS)
    ]
    pool.write_text("".join(i.model_dump_json() + "\n" for i in items), "utf-8")
    base = tmp_path / "hybrid.run"
    hits = [
        RunHit(qid="q1", chunk=_ref(n), rank=n + 1, score=1.0 / (n + 1), system="hybrid")
        for n in range(3)
    ]
    base.write_text(run_text(hits), "utf-8")
    return {"questions": questions, "pool": pool, "base": base, "dir": tmp_path / "model"}


def _model(directory: Path, trained_on: tuple[str, ...]) -> None:
    model, _ = write_tiny_model(directory)
    manifest = RerankerManifest(
        name="tiny",
        base_model="tiny",
        max_length=64,
        trained_on=trained_on,
        onnx_sha256=sha256_of(model),
        created_at=dt.datetime(2026, 11, 13, tzinfo=dt.UTC),
    )
    (directory / MANIFEST_FILE).write_text(manifest.model_dump_json(), "utf-8")


def _common(files: dict[str, Path]) -> list[str]:
    return [
        "--model",
        str(files["dir"]),
        "--base-run",
        str(files["base"]),
        "--pool",
        str(files["pool"]),
        "--questions",
        str(files["questions"]),
        "--split-file",
        str(SPLIT_FILE),
        "--depth",
        "3",
    ]


def test_run_writes_the_reranked_trec_run(files: dict[str, Path], tmp_path: Path) -> None:
    _model(files["dir"], ())
    out = tmp_path / "out.run"
    argv = ["rerank", "run", *_common(files), "--system", "hybrid+rr", "--out", str(out)]
    assert main(argv) == 0
    hits = parse_run(out.read_text("utf-8"))
    expected = sorted(range(3), key=lambda n: -tiny_score(QUESTION, TEXTS[n]))
    assert [h.chunk.ordinal for h in sorted(hits, key=lambda h: h.rank)] == expected
    assert {h.system for h in hits} == {"hybrid+rr"}


def test_run_refuses_a_model_trained_on_the_question_company(
    files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _model(files["dir"], ("COP", "CVX"))
    argv = ["rerank", "run", *_common(files), "--system", "x", "--out", str(tmp_path / "o.run")]
    assert main(argv) == 1
    assert "COP" in capsys.readouterr().err


def test_bench_records_latency_percentiles(files: dict[str, Path], tmp_path: Path) -> None:
    _model(files["dir"], ())
    runs = tmp_path / "runs.csv"
    argv = ["rerank", "bench", *_common(files), "--repeats", "2", "--record", str(runs)]
    assert main([*argv, "--git-sha", "abc1234"]) == 0
    rows = list(csv.DictReader(runs.open(encoding="utf-8")))
    assert [r["metric"] for r in rows] == ["L1_rerank_p50", "L1_rerank_p95"]
    assert {r["unit"] for r in rows} == {"ms"}
    assert {r["n"] for r in rows} == {"2"}
    assert all(float(r["value"]) > 0 for r in rows)
    assert {r["system"] for r in rows} == {"tiny"}
