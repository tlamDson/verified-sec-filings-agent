"""`sec-agent rerank cv|export`: fine-tune by company folds, and export a model to ONNX.

`cv` trains one model per G-ret company on the other companies' labels and reranks the
held-out company's questions with it: every question is scored by a model that never saw
its company. It writes the TREC run and a JSON summary beside it (folds, pair counts,
hyperparameters). `export` writes the model the API serves: the base model as it is
(zero-shot, `trained_on` empty), or with `--train` fine-tuned on every labelled company,
which then must never be scored on G-ret again. Both need the `train` extra.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.golden.gret.models import Label
from sec_agent.golden.gret.trec import run_text
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.rerank.folds import company_folds, training_pairs
from sec_agent.rerank.inputs import add_input_options, read_inputs
from sec_agent.rerank.reranked_runs import FoldScorer, rerank_runs
from sec_agent.rerank.train_torch import TrainConfig, export_onnx, fine_tune

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_BASE_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
CHECK_PAIRS = 64


def add_commands(steps: "Subparsers") -> None:
    cv = steps.add_parser("cv", help="fine-tune per company fold, rerank held-out questions")
    _add_train_options(cv)
    add_input_options(cv, labels=True)
    cv.add_argument("--system", default="hybrid+rerank-ft", help="system name in the run")
    cv.add_argument("--out", type=Path, required=True, help="TREC run to write")
    cv.set_defaults(run=_cv)

    export = steps.add_parser("export", help="export a reranker to ONNX for serving")
    _add_train_options(export)
    add_input_options(export, labels=True)
    export.add_argument("--train", action="store_true", help="fine-tune on every company first")
    export.add_argument("--name", required=True, help="model name in the manifest")
    export.add_argument("--out-dir", type=Path, required=True)
    export.set_defaults(run=_export)


def _add_train_options(parser: argparse.ArgumentParser) -> None:
    defaults = TrainConfig()
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL, help="Hugging Face id or path")
    parser.add_argument("--device", default="cuda", help="torch device (cuda)")
    parser.add_argument("--epochs", type=int, default=defaults.epochs)
    parser.add_argument("--learning-rate", type=float, default=defaults.learning_rate)
    parser.add_argument("--batch-size", type=int, default=defaults.batch_size)
    parser.add_argument("--max-length", type=int, default=defaults.max_length)
    parser.add_argument("--seed", type=int, default=defaults.seed)


def _config(args: argparse.Namespace) -> TrainConfig:
    return TrainConfig(
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        max_length=args.max_length,
        seed=args.seed,
    )


def _cv(args: argparse.Namespace) -> int:
    config = _config(args)
    try:
        inputs = read_inputs(args)
        labels = read_jsonl(args.labels, Label)
        folds = company_folds(q.ticker for q in inputs.questions)
        scorers: dict[str, FoldScorer] = {}
        summary: list[dict[str, object]] = []
        for fold in folds:
            pairs = training_pairs(inputs.questions, inputs.pool, labels, tickers=fold.train)
            model = fine_tune(args.base_model, pairs, config, device=args.device)
            scorers[fold.held_out] = FoldScorer(model, fold.train)
            summary.append({"held_out": fold.held_out, "train": fold.train, "pairs": len(pairs)})
            print(f"fold {fold.held_out}: trained on {len(pairs)} pairs of {len(fold.train)}")
        hits = rerank_runs(
            inputs.questions,
            inputs.base,
            inputs.texts,
            scorers.__getitem__,
            depth=args.depth,
            system=args.system,
        )
    except (ValueError, OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(run_text(hits), "utf-8", newline="\n")
    record = {
        "system": args.system,
        "base_model": args.base_model,
        "base_run": Path(args.base_run).as_posix(),
        "depth": args.depth,
        "cv": "leave-one-company-out",
        "training": config.as_record(),
        "folds": summary,
    }
    summary_text = json.dumps(record, indent=2) + "\n"
    out.with_suffix(".json").write_text(summary_text, "utf-8", newline="\n")
    print(f"wrote {out} and {out.with_suffix('.json').name}")
    return 0


def _export(args: argparse.Namespace) -> int:
    config = _config(args) if args.train else TrainConfig(epochs=0, max_length=args.max_length)
    try:
        inputs = read_inputs(args)
        tickers = sorted({q.ticker for q in inputs.questions}) if args.train else []
        pairs = training_pairs(
            inputs.questions, inputs.pool, read_jsonl(args.labels, Label), tickers=tickers
        )
        model = fine_tune(args.base_model, pairs, config, device=args.device)
        checks = [(p.query, p.passage) for p in pairs[:CHECK_PAIRS]] or [
            (q.question, inputs.texts[h.chunk.docid])
            for q in inputs.questions[:4]
            for h in inputs.base
            if h.qid == q.id and h.rank <= 16
        ]
        manifest = export_onnx(
            model,
            args.out_dir,
            name=args.name,
            base_model=args.base_model,
            trained_on=tuple(tickers),
            training=config.as_record() | {"pairs": len(pairs)},
            check_pairs=checks,
        )
    except (ValueError, OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"exported {manifest.name} to {args.out_dir}: trained on {len(tickers)} companies,"
        f" ONNX vs torch max |diff| {manifest.parity_max_abs_diff}"
    )
    return 0
