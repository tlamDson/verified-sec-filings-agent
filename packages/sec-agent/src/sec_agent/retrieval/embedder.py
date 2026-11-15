"""The embedding model as the index sees it, and the checks around every call."""

from collections.abc import Sequence
from typing import Protocol

from sec_agent.retrieval.errors import EmbeddingMismatchError
from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.vectors import check_vector


class Embedder(Protocol):
    @property
    def spec(self) -> EmbedderSpec: ...

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text; prefixes are already applied."""
        ...

    def count_tokens(self, texts: Sequence[str]) -> list[int]:
        """Model tokens per text, special tokens included, before truncation."""
        ...


def embed_passages(embedder: Embedder, texts: Sequence[str]) -> list[list[float]]:
    prefix = embedder.spec.passage_prefix
    return _checked(embedder, [prefix + text for text in texts])


def embed_query(embedder: Embedder, text: str) -> list[float]:
    return _checked(embedder, [embedder.spec.query_prefix + text])[0]


def count_truncated(embedder: Embedder, texts: Sequence[str]) -> int:
    """Passages longer than the model reads; their tail is not in their vector."""
    limit = embedder.spec.max_input_tokens
    if limit is None or not texts:
        return 0
    prefix = embedder.spec.passage_prefix
    return sum(1 for n in embedder.count_tokens([prefix + t for t in texts]) if n > limit)


def _checked(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    vectors = embedder.encode(texts)
    if len(vectors) != len(texts):
        raise EmbeddingMismatchError(
            f"{embedder.spec.model} returned {len(vectors)} vectors for {len(texts)} texts"
        )
    for vector in vectors:
        check_vector(vector, embedder.spec)
    return vectors
