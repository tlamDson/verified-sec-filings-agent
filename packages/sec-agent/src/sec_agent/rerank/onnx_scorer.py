"""A cross-encoder exported to ONNX, scored with ONNX Runtime on CPU: the served reranker.

No torch at serving time: `tokenizers` encodes each (query, passage) pair, truncated to
`max_length` tokens by cutting the passage (never the query), and the model's logit
for the pair is its score. Only the inputs the graph declares are fed (`token_type_ids`
only for models that have it). `onnxruntime` is untyped, so it is reached through a narrow
protocol.
"""

import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
from tokenizers import Encoding, Tokenizer

_PAD_TOKENS = ("[PAD]", "<pad>")


class _Arg(Protocol):
    name: str


class _Session(Protocol):
    def get_inputs(self) -> list[_Arg]: ...

    def get_outputs(self) -> list[_Arg]: ...

    def run(self, output_names: list[str], feed: dict[str, Any]) -> list[Any]: ...


class OnnxCrossEncoder:
    def __init__(
        self,
        model_path: Path,
        tokenizer_path: Path,
        *,
        max_length: int,
        name: str,
        batch_size: int = 16,
        threads: int | None = None,
    ) -> None:
        ort: Any = importlib.import_module("onnxruntime")
        options = ort.SessionOptions()
        if threads is not None:
            options.intra_op_num_threads = threads
        self._session = cast(
            _Session,
            ort.InferenceSession(
                str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
            ),
        )
        self._inputs = {arg.name for arg in self._session.get_inputs()}
        if not {"input_ids", "attention_mask"} <= self._inputs:
            raise ValueError(f"{model_path.name}: want input_ids and attention_mask inputs")
        self._output = self._session.get_outputs()[0].name
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.no_padding()
        untyped_tokenizer: Any = self._tokenizer  # enable_truncation has untyped **kwargs
        untyped_tokenizer.enable_truncation(max_length, strategy="only_second")
        self._pad_id = _pad_id(self._tokenizer)
        self._name, self._batch_size = name, batch_size

    @property
    def name(self) -> str:
        return self._name

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        scores: list[float] = []
        for start in range(0, len(passages), self._batch_size):
            batch = passages[start : start + self._batch_size]
            encodings = self._tokenizer.encode_batch([(query, p) for p in batch])
            scores += self._logits(encodings)
        return scores

    def _logits(self, encodings: list[Encoding]) -> list[float]:
        width = max(len(e.ids) for e in encodings)
        shape = (len(encodings), width)
        ids = np.full(shape, self._pad_id, dtype=np.int64)
        mask = np.zeros(shape, dtype=np.int64)
        types = np.zeros(shape, dtype=np.int64)
        for row, e in enumerate(encodings):
            n = len(e.ids)
            ids[row, :n], mask[row, :n], types[row, :n] = e.ids, 1, e.type_ids
        feed: dict[str, Any] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = types
        logits = np.asarray(self._session.run([self._output], feed)[0], dtype=np.float64)
        if logits.ndim == 2 and logits.shape[1] == 1:
            logits = logits[:, 0]
        if logits.shape != (len(encodings),):
            raise ValueError(f"reranker output has shape {logits.shape}; want one logit a pair")
        return [float(x) for x in logits]


def _pad_id(tokenizer: Tokenizer) -> int:
    untyped: Any = tokenizer
    padding = cast(dict[str, Any] | None, untyped.padding)
    if padding is not None:
        return int(padding["pad_id"])
    for token in _PAD_TOKENS:
        if (found := tokenizer.token_to_id(token)) is not None:
            return found
    return 0
