"""`sec-agent rerank run|bench|cv|export`: the reranker's R1 runs, latency, and models.

`run` and `bench` use an exported ONNX model on CPU, as the API serves it; `cv` and
`export` (in `train_cli`) need the `train` extra. Scores come from the R1 scorer:
`sec-agent eval retrieval score --run ... --baseline hybrid --record runs.csv`.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.eval.output import add_record_options, record_rows
from sec_agent.golden.gret.trec import run_text
from sec_agent.rerank import train_cli
from sec_agent.rerank.inputs import add_input_options, candidates, read_inputs
from sec_agent.rerank.latency import latency_rows, percentile
from sec_agent.rerank.loader import RerankerLoadError, load_reranker
from sec_agent.rerank.reranked_runs import FoldScorer, rerank_runs

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    rerank = subparsers.add_parser("rerank", help="cross-encoder reranker: runs, latency, models")
    steps = rerank.add_subparsers(dest="rerank_command", metavar="step", required=True)

    run = steps.add_parser("run", help="rerank a base run's top chunks with an ONNX model")
    _add_model_options(run)
    add_input_options(run)
    run.add_argument("--system", required=True, help="system name in the written run")
    run.add_argument("--out", type=Path, required=True, help="TREC run to write")
    run.set_defaults(run=_run)

    bench = steps.add_parser("bench", help="CPU latency of reranking each question's chunks")
    _add_model_options(bench)
    add_input_options(bench)
    bench.add_argument("--repeats", type=int, default=3, help="passes over the questions (3)")
    add_record_options(bench)
    bench.set_defaults(run=_bench)

    train_cli.add_commands(steps)


def _add_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", type=Path, required=True, help="exported reranker directory")
    parser.add_argument("--threads", type=int, default=None, help="ONNX Runtime threads")
    parser.add_argument("--batch-size", type=int, default=16)


def _run(args: argparse.Namespace) -> int:
    try:
        inputs = read_inputs(args)
        loaded = load_reranker(args.model, batch_size=args.batch_size, threads=args.threads)
        fold = FoldScorer(loaded.scorer, loaded.manifest.trained_on)
        hits = rerank_runs(
            inputs.questions,
            inputs.base,
            inputs.texts,
            lambda _ticker: fold,
            depth=args.depth,
            system=args.system,
        )
    except (ValueError, OSError, RerankerLoadError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(run_text(hits), "utf-8", newline="\n")
    print(f"wrote {len({h.qid for h in hits})} questions reranked by {fold.scorer.name} to {out}")
    return 0


def _bench(args: argparse.Namespace) -> int:
    if args.repeats < 1:
        print("error: --repeats must be at least 1", file=sys.stderr)
        return 2
    try:
        inputs = read_inputs(args)
        loaded = load_reranker(args.model, batch_size=args.batch_size, threads=args.threads)
        work = candidates(inputs, args.depth)
    except (ValueError, OSError, RerankerLoadError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if not work:
        print("error: no question has base hits", file=sys.stderr)
        return 1
    loaded.scorer.score(work[0][0].question, work[0][1])  # warm-up, not timed
    timings: list[float] = []
    for _ in range(args.repeats):
        for question, texts in work:
            start = time.perf_counter()
            loaded.scorer.score(question.question, texts)
            timings.append((time.perf_counter() - start) * 1000)
    print(
        f"{loaded.manifest.name}: {len(timings)} calls of up to {args.depth} chunks;"
        f" p50 {percentile(timings, 50):.1f} ms, p95 {percentile(timings, 95):.1f} ms"
    )
    config = f"depth={args.depth};batch={args.batch_size};threads={args.threads or 'default'}"
    return record_rows(
        args,
        lambda date, sha: latency_rows(
            timings, system=loaded.manifest.name, config=config, date=date, git_sha=sha
        ),
    )
