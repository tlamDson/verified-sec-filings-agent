"""What every `sec-agent rerank` command reads: G-ret questions, a base run and pool texts.

All from files: the base run is the committed hybrid run, and every chunk in its top 20 is
in the G-ret pool (the pool is the top 20 of each system), so its text is there too.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from sec_agent.golden.gret.cli import DEFAULT_LABELS, DEFAULT_POOL, DEFAULT_QUESTIONS
from sec_agent.golden.gret.models import PoolItem, RetQuestion, RunHit
from sec_agent.golden.gret.questions import load_questions
from sec_agent.golden.gret.trec import parse_run
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.golden.split import DEFAULT_SPLIT_FILE, read_split
from sec_agent.rerank.folds import pool_texts

DEFAULT_BASE_RUN = Path("results/retrieval/v1/hybrid.run")
DEFAULT_DEPTH = 20


@dataclass(frozen=True)
class RerankInputs:
    questions: list[RetQuestion]
    base: list[RunHit]
    pool: list[PoolItem]
    texts: dict[str, str]


def add_input_options(parser: argparse.ArgumentParser, *, labels: bool = False) -> None:
    parser.add_argument("--base-run", type=Path, default=DEFAULT_BASE_RUN, help="run to rerank")
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL, help="G-ret pool (texts)")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--split-file", type=Path, default=DEFAULT_SPLIT_FILE)
    parser.add_argument(
        "--depth", type=int, default=DEFAULT_DEPTH, help=f"chunks reranked ({DEFAULT_DEPTH})"
    )
    if labels:
        parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)


def read_inputs(args: argparse.Namespace) -> RerankInputs:
    """Raises ValueError or OSError with the file named."""
    if args.depth < 1:
        raise ValueError("--depth must be at least 1")
    questions = load_questions(args.questions, read_split(args.split_file))
    try:
        base = parse_run(Path(args.base_run).read_text("utf-8"))
    except ValueError as error:
        raise ValueError(f"{Path(args.base_run).name}: {error}") from error
    pool = read_jsonl(args.pool, PoolItem)
    return RerankInputs(questions=questions, base=base, pool=pool, texts=pool_texts(pool))


def candidates(inputs: RerankInputs, depth: int) -> list[tuple[RetQuestion, list[str]]]:
    """Each question with the texts of its base run's top `depth` chunks, best first."""
    by_qid: dict[str, list[RunHit]] = {}
    for hit in inputs.base:
        by_qid.setdefault(hit.qid, []).append(hit)
    out: list[tuple[RetQuestion, list[str]]] = []
    for q in inputs.questions:
        hits = sorted(by_qid.get(q.id, []), key=lambda h: (h.rank, h.chunk.docid))[:depth]
        if missing := [h.chunk.docid for h in hits if h.chunk.docid not in inputs.texts]:
            raise ValueError(f"{q.id}: no text for {missing[:3]}")
        if hits:
            out.append((q, [inputs.texts[h.chunk.docid] for h in hits]))
    return out
