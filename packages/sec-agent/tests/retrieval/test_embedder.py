"""Embedding helpers: prefixes applied, every vector checked before it reaches the index."""

import math
from collections.abc import Sequence

import pytest
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.retrieval.embedder import embed_passages, embed_query
from sec_agent.retrieval.errors import EmbeddingMismatchError
from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.vectors import vector_literal


class _Fixed:
    """Returns the given vectors whatever it is asked."""

    def __init__(self, vectors: list[list[float]], spec: EmbedderSpec = HASH_SPEC) -> None:
        self._vectors, self._spec = vectors, spec

    @property
    def spec(self) -> EmbedderSpec:
        return self._spec

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return self._vectors

    def count_tokens(self, texts: Sequence[str]) -> list[int]:
        return [1 for _ in texts]


def _unit(dims: int) -> list[float]:
    return [1.0] + [0.0] * (dims - 1)


def test_passages_and_queries_get_their_prefixes() -> None:
    embedder = HashEmbedder()
    embed_passages(embedder, ["net sales"])
    embed_query(embedder, "net sales")
    assert embedder.encoded == ["passage: net sales", "query: net sales"]


def test_wrong_dimension_is_refused() -> None:
    with pytest.raises(EmbeddingMismatchError, match="dimensions"):
        embed_passages(HashEmbedder(wrong_dimensions=True), ["a"])


def test_wrong_count_is_refused() -> None:
    with pytest.raises(EmbeddingMismatchError, match="2 texts"):
        embed_passages(_Fixed([_unit(16)]), ["a", "b"])


def test_non_finite_values_are_refused() -> None:
    with pytest.raises(EmbeddingMismatchError, match="finite"):
        embed_passages(_Fixed([[math.nan] + [0.0] * 15]), ["a"])


def test_a_normalised_space_refuses_vectors_that_are_not_unit_length() -> None:
    with pytest.raises(EmbeddingMismatchError, match="unit length"):
        embed_passages(_Fixed([[2.0] + [0.0] * 15]), ["a"])
    unnormalised = HASH_SPEC.model_copy(update={"normalized": False})
    assert embed_passages(_Fixed([[2.0] + [0.0] * 15], unnormalised), ["a"])[0][0] == 2.0


def test_vector_literal_is_pgvector_text() -> None:
    assert vector_literal([0.5, -1.0, 0.0], 3) == "[0.5,-1.0,0.0]"
    with pytest.raises(EmbeddingMismatchError):
        vector_literal([0.5], 3)
