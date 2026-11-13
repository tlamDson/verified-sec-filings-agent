"""The embedding model: a sentence-transformers model on the local GPU (or CPU).

`sentence-transformers` and `torch` are the optional `embed` extra, installed with
`uv sync --all-packages --extra embed`; tests and CI never load them. The package is imported
when an embedder is built, through narrow protocols, so type checking does not depend on it.

Default model: BAAI/bge-base-en-v1.5 (768 dimensions, 512 input tokens, MIT licence), with
its documented query instruction and no passage prefix. Vectors are L2-normalised.
"""

import importlib
from collections.abc import Sequence
from typing import Any, Protocol, cast

from sec_agent.retrieval.errors import EmbedderUnavailableError, EmbeddingMismatchError
from sec_agent.retrieval.models import EmbedderSpec

INSTALL_HINT = "uv sync --all-packages --extra embed"

DEFAULT_SPEC = EmbedderSpec(
    model="BAAI/bge-base-en-v1.5",
    dimensions=768,
    normalized=True,
    query_prefix="Represent this sentence for searching relevant passages: ",
    passage_prefix="",
    max_input_tokens=512,
)


class _Array(Protocol):
    def tolist(self) -> list[list[float]]: ...


class _Model(Protocol):
    max_seq_length: int
    tokenizer: Any

    def encode(self, sentences: list[str], **kwargs: Any) -> _Array: ...


class SentenceTransformerEmbedder:
    def __init__(
        self, spec: EmbedderSpec = DEFAULT_SPEC, *, device: str | None = None, batch_size: int = 32
    ) -> None:
        try:
            module = importlib.import_module("sentence_transformers")
        except ImportError as error:
            raise EmbedderUnavailableError(
                f"sentence-transformers is not installed; install it with `{INSTALL_HINT}`"
            ) from error
        loaded: Any = module.SentenceTransformer(spec.model, device=device)
        # Renamed in sentence-transformers 6; the old name still works there, with a warning.
        dimension = getattr(loaded, "get_embedding_dimension", None)
        dims = (dimension or loaded.get_sentence_embedding_dimension)()
        model = cast(_Model, loaded)
        if dims != spec.dimensions:
            raise EmbeddingMismatchError(
                f"{spec.model} returns {dims} dimensions; the spec says {spec.dimensions}"
            )
        if spec.max_input_tokens is not None:
            model.max_seq_length = spec.max_input_tokens
        self._spec, self._model, self._batch_size = spec, model, batch_size

    @property
    def spec(self) -> EmbedderSpec:
        return self._spec

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=self._spec.normalized,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def count_tokens(self, texts: Sequence[str]) -> list[int]:
        encoded = self._model.tokenizer(list(texts), add_special_tokens=True, truncation=False)
        ids = cast(list[list[int]], encoded["input_ids"])
        return [len(row) for row in ids]
