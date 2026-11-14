"""Fine-tune a cross-encoder on G-ret pairs (torch, GPU), and export it to ONNX.

`torch` and `transformers` are the optional `train` extra; tests without it skip, and CI
never loads them, so both are reached through `importlib` and typed as `Any` here.

Training is pointwise: one logit per (question, chunk), binary cross-entropy against the
soft label grade / 2, AdamW with linear warmup and decay, gradient norm clipped at 1. The
order of pairs in each epoch comes from a seeded generator, so a run is reproducible on
one device. Hyperparameters are fixed in `TrainConfig` before any score is seen: G-ret has
no dev questions to tune them on, and tuning on the CV folds would leak.
"""

import copy
import datetime as dt
import importlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sec_agent.rerank.folds import TrainPair
from sec_agent.rerank.loader import file_sha256
from sec_agent.rerank.models import MANIFEST_FILE, MODEL_FILE, TOKENIZER_FILE, RerankerManifest
from sec_agent.rerank.onnx_scorer import OnnxCrossEncoder

INSTALL_HINT = "uv sync --all-packages --extra train"
ONNX_OPSET = 17
_INPUTS = ("input_ids", "attention_mask", "token_type_ids")


@dataclass(frozen=True)
class TrainConfig:
    epochs: int = 2
    learning_rate: float = 2e-5
    batch_size: int = 16
    warmup_fraction: float = 0.1
    weight_decay: float = 0.01
    max_length: int = 512
    seed: int = 20261113

    def as_record(self) -> dict[str, str | int | float]:
        return dict(asdict(self))


def _modules() -> tuple[Any, Any]:
    try:
        return importlib.import_module("torch"), importlib.import_module("transformers")
    except ImportError as error:
        raise RuntimeError(f"torch and transformers are needed: `{INSTALL_HINT}`") from error


class TorchCrossEncoder:
    def __init__(self, model: Any, tokenizer: Any, *, max_length: int, device: str) -> None:
        self.model, self.tokenizer = model, tokenizer
        self.max_length, self.device = max_length, device

    @classmethod
    def load(cls, base: str, *, max_length: int, device: str) -> "TorchCrossEncoder":
        _, transformers = _modules()
        tokenizer = transformers.AutoTokenizer.from_pretrained(base)
        model = transformers.AutoModelForSequenceClassification.from_pretrained(base)
        if model.config.num_labels != 1:
            raise ValueError(f"{base}: want a cross-encoder with one output logit")
        model.to(device).eval()
        return cls(model, tokenizer, max_length=max_length, device=device)

    @property
    def name(self) -> str:
        return str(self.model.config.name_or_path)

    def encode(self, queries: Sequence[str], passages: Sequence[str]) -> Any:
        return self.tokenizer(
            list(queries),
            list(passages),
            truncation="only_second",
            max_length=self.max_length,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

    def score(self, query: str, passages: Sequence[str], batch_size: int = 32) -> list[float]:
        torch, _ = _modules()
        self.model.eval()
        scores: list[float] = []
        with torch.inference_mode():
            for start in range(0, len(passages), batch_size):
                batch = list(passages[start : start + batch_size])
                logits = self.model(**self.encode([query] * len(batch), batch)).logits
                scores += [float(x) for x in logits.view(-1).float().cpu().tolist()]
        return scores


def fine_tune(
    base: str, pairs: Sequence[TrainPair], config: TrainConfig, *, device: str
) -> TorchCrossEncoder:
    """`base` fine-tuned on `pairs`; with `epochs = 0`, `base` unchanged."""
    torch, transformers = _modules()
    transformers.set_seed(config.seed)
    encoder = TorchCrossEncoder.load(base, max_length=config.max_length, device=device)
    if config.epochs == 0 or not pairs:
        return encoder
    model = encoder.model
    steps = config.epochs * -(-len(pairs) // config.batch_size)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    schedule = transformers.get_linear_schedule_with_warmup(
        optimizer, int(steps * config.warmup_fraction), steps
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()
    generator = torch.Generator().manual_seed(config.seed)
    model.train()
    for _ in range(config.epochs):
        order: list[int] = torch.randperm(len(pairs), generator=generator).tolist()
        for start in range(0, len(order), config.batch_size):
            batch = [pairs[i] for i in order[start : start + config.batch_size]]
            tokens = encoder.encode([p.query for p in batch], [p.passage for p in batch])
            labels = torch.tensor([p.label for p in batch], device=device)
            loss = loss_fn(model(**tokens).logits.view(-1), labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            schedule.step()
            optimizer.zero_grad()
    model.eval()
    return encoder


def export_onnx(
    encoder: TorchCrossEncoder,
    out_dir: Path,
    *,
    name: str,
    base_model: str,
    trained_on: tuple[str, ...],
    training: dict[str, str | int | float],
    check_pairs: Sequence[tuple[str, str]],
) -> RerankerManifest:
    """Write model.onnx, tokenizer.json and the manifest; check ONNX against torch on
    `check_pairs` and record the largest difference."""
    torch, _ = _modules()
    out_dir.mkdir(parents=True, exist_ok=True)
    model = copy.deepcopy(encoder.model).to("cpu").eval()
    sample = encoder.tokenizer(["query"], ["passage"], return_tensors="pt")
    names = [n for n in _INPUTS if n in sample]
    dynamic = {n: {0: "batch", 1: "sequence"} for n in names} | {"logits": {0: "batch"}}
    torch.onnx.export(
        _ByName(torch, model, names),
        tuple(sample[n] for n in names),
        str(out_dir / MODEL_FILE),
        input_names=names,
        output_names=["logits"],
        dynamic_axes=dynamic,
        opset_version=ONNX_OPSET,
        dynamo=False,
    )
    encoder.tokenizer.backend_tokenizer.save(str(out_dir / TOKENIZER_FILE))
    onnx_scorer = OnnxCrossEncoder(
        out_dir / MODEL_FILE, out_dir / TOKENIZER_FILE, max_length=encoder.max_length, name=name
    )
    manifest = RerankerManifest(
        name=name,
        base_model=base_model,
        max_length=encoder.max_length,
        trained_on=tuple(sorted(trained_on)),
        onnx_sha256=file_sha256(out_dir / MODEL_FILE),
        training=training,
        parity_max_abs_diff=_parity(encoder, onnx_scorer, check_pairs),
        created_at=dt.datetime.now(dt.UTC),
    )
    (out_dir / MANIFEST_FILE).write_text(manifest.model_dump_json(indent=2) + "\n", "utf-8")
    return manifest


def _parity(
    encoder: TorchCrossEncoder, onnx_scorer: OnnxCrossEncoder, pairs: Sequence[tuple[str, str]]
) -> float | None:
    by_query: defaultdict[str, list[str]] = defaultdict(list)
    for query, passage in pairs:
        by_query[query].append(passage)
    diffs = [
        abs(a - b)
        for query, passages in by_query.items()
        for a, b in zip(
            encoder.score(query, passages), onnx_scorer.score(query, passages), strict=True
        )
    ]
    return max(diffs) if diffs else None


def _by_name_module(torch: Any) -> Any:
    class ByName(torch.nn.Module):
        """Positional ONNX inputs to the keyword arguments the model takes; logits out."""

        def __init__(self, model: Any, names: list[str]) -> None:
            super().__init__()  # pyright: ignore[reportUnknownMemberType]
            self.model, self.names = model, names

        def forward(self, *inputs: Any) -> Any:
            return self.model(**dict(zip(self.names, inputs, strict=True))).logits

    return ByName


def _ByName(torch: Any, model: Any, names: list[str]) -> Any:  # noqa: N802
    return _by_name_module(torch)(model, names)
