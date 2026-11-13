"""The sentence-transformers adapter, against a stand-in module: no model download, no GPU."""

import sys
import types
from collections.abc import Sequence
from typing import Any, ClassVar

import pytest

from sec_agent.retrieval.errors import EmbedderUnavailableError, EmbeddingMismatchError
from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.sentence_transformer import DEFAULT_SPEC, SentenceTransformerEmbedder

SPEC = EmbedderSpec(model="org/tiny", dimensions=3, normalized=True, max_input_tokens=8)


class _Array:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


class _Tokenizer:
    def __call__(self, texts: list[str], **kwargs: Any) -> dict[str, list[list[int]]]:
        _Model.tokenizer_kwargs = kwargs
        return {"input_ids": [[0] * (len(t.split()) + 2) for t in texts]}


class _Model:
    instances: ClassVar[list["_Model"]] = []
    tokenizer_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, name: str, device: str | None = None, revision: str | None = None) -> None:
        self.name, self.device, self.revision = name, device, revision
        self.max_seq_length = 512
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.tokenizer = _Tokenizer()
        _Model.instances.append(self)

    def get_sentence_embedding_dimension(self) -> int:
        return 3

    def encode(self, sentences: Sequence[str], **kwargs: Any) -> _Array:
        self.calls.append((list(sentences), kwargs))
        return _Array([[1.0, 0.0, 0.0] for _ in sentences])


@pytest.fixture
def fake_module(monkeypatch: pytest.MonkeyPatch) -> type[_Model]:
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _Model  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    _Model.instances = []
    return _Model


def test_default_model_is_pinned_in_the_spec() -> None:
    assert DEFAULT_SPEC.model == "BAAI/bge-base-en-v1.5"
    assert DEFAULT_SPEC.dimensions == 768
    assert DEFAULT_SPEC.normalized
    assert DEFAULT_SPEC.query_prefix.startswith("Represent this sentence")
    assert DEFAULT_SPEC.max_input_tokens == 512


def test_loads_the_named_model_on_the_device(fake_module: type[_Model]) -> None:
    embedder = SentenceTransformerEmbedder(SPEC, device="cuda", batch_size=7)
    (model,) = fake_module.instances
    assert (model.name, model.device) == ("org/tiny", "cuda")
    assert model.max_seq_length == 8
    assert embedder.spec == SPEC


def test_encode_asks_for_normalised_vectors_in_batches(fake_module: type[_Model]) -> None:
    embedder = SentenceTransformerEmbedder(SPEC, batch_size=7)
    assert embedder.encode(["a", "b"]) == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    ((texts, kwargs),) = fake_module.instances[0].calls
    assert texts == ["a", "b"]
    assert kwargs["batch_size"] == 7
    assert kwargs["normalize_embeddings"] is True
    assert kwargs["show_progress_bar"] is False


def test_token_counts_use_the_model_tokenizer_without_truncation(
    fake_module: type[_Model],
) -> None:
    embedder = SentenceTransformerEmbedder(SPEC)
    assert embedder.count_tokens(["one two three", "x"]) == [5, 3]
    assert fake_module.tokenizer_kwargs.get("truncation") is False


def test_model_with_another_dimension_is_refused(fake_module: type[_Model]) -> None:
    with pytest.raises(EmbeddingMismatchError, match="768"):
        SentenceTransformerEmbedder(SPEC.model_copy(update={"dimensions": 768}))


def test_missing_package_says_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(EmbedderUnavailableError, match="--extra embed"):
        SentenceTransformerEmbedder(SPEC)
