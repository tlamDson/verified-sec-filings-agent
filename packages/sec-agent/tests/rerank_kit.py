"""Reranker test kit: fake scorers, and a tiny cross-encoder in ONNX built on the spot.

The tiny model scores a pair by the sum of its token ids (padding masked out), with a
word-level tokenizer whose ids are known, so a test can predict every score. Nothing is
downloaded.
"""

import hashlib
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import onnx
from onnx import TensorProto, helper
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from tokenizers.processors import TemplateProcessing

WORDS = ("revenue", "fell", "rose", "supplier", "risk", "the", "oil", "price")
VOCAB = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3} | {
    w: 10 * (i + 1) for i, w in enumerate(WORDS)
}


def tiny_tokenizer() -> Tokenizer:
    tokenizer = Tokenizer(WordLevel(VOCAB, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()  # pyright: ignore[reportAttributeAccessIssue]
    tokenizer.post_processor = TemplateProcessing(  # pyright: ignore[reportAttributeAccessIssue]
        single="[CLS] $A [SEP]",
        pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", 2), ("[SEP]", 3)],
    )
    return tokenizer


def tiny_score(query: str, passage: str, max_length: int = 64) -> float:
    """What the tiny model gives a pair: sum of the ids, after truncating the passage."""
    encoding = tiny_tokenizer()
    encoding.enable_truncation(max_length, strategy="only_second")
    return float(sum(encoding.encode(query, passage).ids))


def tiny_onnx_model(with_token_types: bool = True) -> onnx.ModelProto:
    """logits[b, 0] = sum_l input_ids[b, l] * attention_mask[b, l], as float."""
    inputs = [
        helper.make_tensor_value_info("input_ids", TensorProto.INT64, ["batch", "seq"]),
        helper.make_tensor_value_info("attention_mask", TensorProto.INT64, ["batch", "seq"]),
    ]
    if with_token_types:
        inputs.append(
            helper.make_tensor_value_info("token_type_ids", TensorProto.INT64, ["batch", "seq"])
        )
    axes = helper.make_tensor("axes", TensorProto.INT64, [1], [1])
    nodes = [
        helper.make_node("Mul", ["input_ids", "attention_mask"], ["masked"]),
        helper.make_node("ReduceSum", ["masked", "axes"], ["summed"], keepdims=1),
        helper.make_node("Cast", ["summed"], ["logits"], to=TensorProto.FLOAT),
    ]
    output = helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", 1])
    graph = helper.make_graph(nodes, "tiny", inputs, [output], initializer=[axes])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model


def write_tiny_model(directory: Path, with_token_types: bool = True) -> tuple[Path, Path]:
    """model.onnx and tokenizer.json in `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    model_path, tokenizer_path = directory / "model.onnx", directory / "tokenizer.json"
    onnx.save(tiny_onnx_model(with_token_types), str(model_path))
    tiny_tokenizer().save(str(tokenizer_path))
    return model_path, tokenizer_path


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeScorer:
    """Scores a passage by a function of its text; counts calls."""

    def __init__(self, fn: Callable[[str, str], float], name: str = "fake") -> None:
        self._fn, self._name = fn, name
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    @property
    def name(self) -> str:
        return self._name

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        self.calls.append((query, tuple(passages)))
        return [self._fn(query, p) for p in passages]


def by_length(_query: str, passage: str) -> float:
    return float(len(passage))


class BlockingScorer:
    """Waits for `release` before answering: a reranker that is slow or hung."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Event()

    @property
    def name(self) -> str:
        return "blocking"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        self.started.set()
        self.release.wait(5)
        return [0.0 for _ in passages]


class BrokenScorer:
    """Raises, or answers with the wrong shape."""

    def __init__(self, answer: Callable[[Sequence[str]], list[float]] | None = None) -> None:
        self._answer = answer

    @property
    def name(self) -> str:
        return "broken"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if self._answer is None:
            raise RuntimeError("model crashed")
        return self._answer(passages)
