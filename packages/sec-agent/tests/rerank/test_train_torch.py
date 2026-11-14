"""Fine-tuning and ONNX export, on a tiny randomly initialised BERT built here (no download).

Needs the `train` extra (torch, transformers, onnx); skipped without it, as in CI.
"""

from pathlib import Path
from typing import Any

import pytest

from sec_agent.rerank.folds import TrainPair
from sec_agent.rerank.loader import load_reranker

transformers: Any = pytest.importorskip("transformers")
pytest.importorskip("torch")

from sec_agent.rerank.train_torch import (  # noqa: E402
    TorchCrossEncoder,
    TrainConfig,
    export_onnx,
    fine_tune,
)

WORDS = ["revenue", "rose", "fell", "oil", "price", "risk", "supplier", "the", "did"]


def _tiny_base(directory: Path) -> str:
    directory.mkdir(parents=True)
    tokens = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *WORDS]
    tokenizer = transformers.BertTokenizerFast(vocab={t: i for i, t in enumerate(tokens)})
    config = transformers.BertConfig(
        vocab_size=len(WORDS) + 5,
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
        max_position_embeddings=64,
        num_labels=1,
    )
    transformers.set_seed(0)
    model = transformers.BertForSequenceClassification(config)
    model.save_pretrained(directory)
    tokenizer.save_pretrained(directory)
    return str(directory)


def _pairs() -> list[TrainPair]:
    up = TrainPair(
        qid="q1", ticker="AAA", query="did revenue rise", passage="revenue rose", label=1.0
    )
    down = TrainPair(
        qid="q1", ticker="AAA", query="did revenue rise", passage="revenue fell", label=0.0
    )
    return [up, down] * 8


CONFIG = TrainConfig(epochs=20, learning_rate=5e-3, batch_size=4, max_length=32, seed=7)


def test_zero_epochs_is_the_base_model(tmp_path: Path) -> None:
    base = _tiny_base(tmp_path / "base")
    a = fine_tune(base, _pairs(), TrainConfig(epochs=0, max_length=32), device="cpu")
    b = TorchCrossEncoder.load(base, max_length=32, device="cpu")
    assert a.score("did revenue rise", ["revenue rose"]) == b.score(
        "did revenue rise", ["revenue rose"]
    )


def test_fine_tuning_learns_the_labels_and_is_seeded(tmp_path: Path) -> None:
    base = _tiny_base(tmp_path / "base")
    first = fine_tune(base, _pairs(), CONFIG, device="cpu")
    again = fine_tune(base, _pairs(), CONFIG, device="cpu")
    rose, fell = first.score("did revenue rise", ["revenue rose", "revenue fell"])
    assert rose > fell
    assert again.score("did revenue rise", ["revenue rose", "revenue fell"]) == [rose, fell]


def test_export_matches_torch_and_loads_with_its_manifest(tmp_path: Path) -> None:
    base = _tiny_base(tmp_path / "base")
    model = fine_tune(base, _pairs(), CONFIG, device="cpu")
    out = tmp_path / "onnx"
    manifest = export_onnx(
        model,
        out,
        name="tiny-ft",
        base_model="tiny",
        trained_on=("AAA",),
        training=CONFIG.as_record(),
        check_pairs=[("did revenue rise", "revenue rose"), ("oil price risk", "supplier risk")],
    )
    assert manifest.trained_on == ("AAA",)
    assert manifest.parity_max_abs_diff is not None
    assert manifest.parity_max_abs_diff < 1e-4
    loaded = load_reranker(out)
    passages = ["revenue rose", "revenue fell", "the oil price"]
    expected = model.score("did revenue rise", passages)
    got = loaded.scorer.score("did revenue rise", passages)
    assert got == pytest.approx(expected, abs=1e-4)
