"""`--reranker DIR` for the servers: loaded at start, or an error; none when not asked."""

import argparse
import datetime as dt
from pathlib import Path

import pytest
from rerank_kit import sha256_of, write_tiny_model

from sec_agent.rerank.loader import RerankerLoadError
from sec_agent.rerank.models import MANIFEST_FILE, RerankerManifest
from sec_agent.rerank.serving import RERANKER_ENV_VAR, add_reranker_option, reranker_from_args


def _args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_reranker_option(parser)
    return parser.parse_args(argv)


def _model(directory: Path) -> Path:
    model, _ = write_tiny_model(directory)
    manifest = RerankerManifest(
        name="tiny-served",
        base_model="tiny",
        max_length=64,
        trained_on=(),
        onnx_sha256=sha256_of(model),
        created_at=dt.datetime(2026, 11, 13, tzinfo=dt.UTC),
    )
    (directory / MANIFEST_FILE).write_text(manifest.model_dump_json(), "utf-8")
    return directory


def test_no_option_no_reranker() -> None:
    assert reranker_from_args(_args([]), {}) is None


def test_the_option_loads_the_model(tmp_path: Path) -> None:
    reranker = reranker_from_args(_args(["--reranker", str(_model(tmp_path))]), {})
    assert reranker is not None
    assert reranker.name == "tiny-served"
    assert reranker.rerank("the oil price", ["revenue", "the oil price"]).order == (1, 0)


def test_the_environment_names_a_default(tmp_path: Path) -> None:
    reranker = reranker_from_args(_args([]), {RERANKER_ENV_VAR: str(_model(tmp_path))})
    assert reranker is not None


def test_a_directory_that_does_not_load_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RerankerLoadError):
        reranker_from_args(_args(["--reranker", str(tmp_path)]), {})


def test_a_bad_timeout_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RerankerLoadError, match="timeout"):
        reranker_from_args(_args(["--reranker", str(tmp_path), "--rerank-timeout", "0"]), {})
