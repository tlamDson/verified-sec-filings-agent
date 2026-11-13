"""A deterministic stand-in for the embedding model, so retrieval tests need no GPU or network.

Shared by the retrieval tests; pytest puts this directory on sys.path (`pythonpath`).
Bag of words hashed into a few dimensions, then L2-normalised: texts sharing words are close.
"""

import hashlib
import math
import re
from collections.abc import Sequence

from sec_agent.retrieval.models import EmbedderSpec

_WORD = re.compile(r"[a-z0-9]+")

HASH_SPEC = EmbedderSpec(
    model="test/hash-bow",
    dimensions=16,
    normalized=True,
    query_prefix="query: ",
    passage_prefix="passage: ",
    max_input_tokens=40,
)


def hash_vector(text: str, dimensions: int) -> list[float]:
    values = [0.0] * dimensions
    for word in _WORD.findall(text.lower()):
        if word in {"query", "passage"}:
            continue  # the prefixes; they would pull every text together
        bucket = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % dimensions
        values[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0.0:
        values[0], norm = 1.0, 1.0
    return [v / norm for v in values]


class HashEmbedder:
    """Records every batch it encodes, so tests can see what was (re-)embedded."""

    def __init__(self, spec: EmbedderSpec = HASH_SPEC, *, wrong_dimensions: bool = False) -> None:
        self._spec = spec
        self._wrong = wrong_dimensions
        self.batches: list[list[str]] = []

    @property
    def spec(self) -> EmbedderSpec:
        return self._spec

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        dims = self._spec.dimensions + (1 if self._wrong else 0)
        return [hash_vector(text, dims) for text in texts]

    def count_tokens(self, texts: Sequence[str]) -> list[int]:
        return [len(_WORD.findall(text.lower())) + 2 for text in texts]  # + [CLS], [SEP]

    @property
    def encoded(self) -> list[str]:
        return [text for batch in self.batches for text in batch]
