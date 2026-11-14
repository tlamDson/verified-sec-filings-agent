"""The served reranker: a cross-encoder in ONNX on CPU, loaded only when its file matches
the manifest."""

import datetime as dt
from pathlib import Path

import pytest
from rerank_kit import sha256_of, tiny_score, write_tiny_model

from sec_agent.rerank.loader import RerankerLoadError, load_reranker
from sec_agent.rerank.models import MANIFEST_FILE, RerankerManifest
from sec_agent.rerank.onnx_scorer import OnnxCrossEncoder

QUERY = "oil price risk"
PASSAGES = ["the oil price fell", "revenue rose", "supplier risk the the the", ""]


@pytest.mark.parametrize("with_token_types", [True, False])
def test_scores_every_pair_in_batches(tmp_path: Path, with_token_types: bool) -> None:
    model, tokenizer = write_tiny_model(tmp_path, with_token_types)
    scorer = OnnxCrossEncoder(model, tokenizer, max_length=64, name="tiny", batch_size=3)
    assert scorer.score(QUERY, PASSAGES) == [tiny_score(QUERY, p) for p in PASSAGES]
    assert scorer.name == "tiny"


def test_long_passages_are_cut_to_max_length(tmp_path: Path) -> None:
    model, tokenizer = write_tiny_model(tmp_path)
    scorer = OnnxCrossEncoder(model, tokenizer, max_length=8, name="tiny")
    long = " ".join(["revenue"] * 50)
    [score] = scorer.score(QUERY, [long])
    assert score == tiny_score(QUERY, long, max_length=8)
    assert score < tiny_score(QUERY, long, max_length=512)


def test_no_passages(tmp_path: Path) -> None:
    model, tokenizer = write_tiny_model(tmp_path)
    assert OnnxCrossEncoder(model, tokenizer, max_length=64, name="tiny").score(QUERY, []) == []


def _manifest(directory: Path, sha: str, trained_on: tuple[str, ...] = ("AAA",)) -> None:
    manifest = RerankerManifest(
        name="tiny-ft",
        base_model="tiny",
        max_length=64,
        trained_on=trained_on,
        onnx_sha256=sha,
        training={"epochs": 1},
        created_at=dt.datetime(2026, 11, 13, tzinfo=dt.UTC),
    )
    (directory / MANIFEST_FILE).write_text(manifest.model_dump_json(indent=2), "utf-8")


def test_load_checks_the_model_digest(tmp_path: Path) -> None:
    model, _ = write_tiny_model(tmp_path)
    _manifest(tmp_path, sha256_of(model))
    loaded = load_reranker(tmp_path)
    assert loaded.manifest.trained_on == ("AAA",)
    assert loaded.scorer.name == "tiny-ft"
    assert loaded.scorer.score(QUERY, PASSAGES[:1]) == [tiny_score(QUERY, PASSAGES[0])]


def test_load_refuses_a_model_that_is_not_the_one_described(tmp_path: Path) -> None:
    write_tiny_model(tmp_path)
    _manifest(tmp_path, "0" * 64)
    with pytest.raises(RerankerLoadError, match="SHA-256"):
        load_reranker(tmp_path)


def test_load_refuses_a_directory_without_a_manifest(tmp_path: Path) -> None:
    write_tiny_model(tmp_path)
    with pytest.raises(RerankerLoadError, match=MANIFEST_FILE):
        load_reranker(tmp_path)


def test_manifest_rejects_a_bad_digest() -> None:
    with pytest.raises(ValueError, match="onnx_sha256"):
        RerankerManifest(
            name="x",
            base_model="b",
            max_length=64,
            trained_on=(),
            onnx_sha256="nothex",
            created_at=dt.datetime(2026, 11, 13, tzinfo=dt.UTC),
        )
