"""b1 with `--lexical`: no query embedder, so the passages come from BM25, not hybrid."""

from typing import Any, cast

import pytest
from eval_data import number_question

from sec_agent.eval.numeric import passages as passages_module
from sec_agent.eval.numeric.passages import SearchPassages
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.models import EmbeddingSpace


def modes_used(monkeypatch: pytest.MonkeyPatch, embedder: Embedder | None) -> list[str]:
    modes: list[str] = []

    def fake_search(*_args: Any, mode: str, **_kwargs: Any) -> list[Any]:
        modes.append(mode)
        return []

    monkeypatch.setattr(passages_module, "search", fake_search)
    source = SearchPassages(cast(Any, None), cast(EmbeddingSpace, None), embedder)
    source.passages(number_question("revenue", "1"), 5)
    return modes


def test_without_an_embedder_b1_searches_bm25_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    assert modes_used(monkeypatch, None) == ["lexical"]


def test_with_an_embedder_b1_searches_hybrid(monkeypatch: pytest.MonkeyPatch) -> None:
    assert modes_used(monkeypatch, cast(Embedder, object())) == ["hybrid"]
