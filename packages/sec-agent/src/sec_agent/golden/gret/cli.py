"""`sec-agent golden pool|label|qrels`: build the G-ret pool, label it, export qrels."""

import argparse
import datetime as dt
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.golden.gret.chunks import PostgresChunkText
from sec_agent.golden.gret.labels import pending_items, qrels_lines
from sec_agent.golden.gret.models import Label, PoolItem
from sec_agent.golden.gret.pool import DEFAULT_DEPTH, attach_text, build_pool, extend_pool
from sec_agent.golden.gret.questions import TARGET_QUESTIONS, load_questions
from sec_agent.golden.gret.session import label_session
from sec_agent.golden.gret.trec import parse_run, qrels_text
from sec_agent.golden.jsonl import append_jsonl, read_jsonl, write_jsonl
from sec_agent.golden.split import read_split
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_QUESTIONS = Path("data/golden/g_ret_questions.jsonl")
DEFAULT_POOL = Path("data/golden/g_ret_pool.jsonl")
DEFAULT_LABELS = Path("data/golden/g_ret_labels.jsonl")
DEFAULT_QRELS = Path("data/golden/g_ret.qrels")
PLANNED_SYSTEMS = 3
POOL_SEED = 20261115


def add_commands(
    actions: "Subparsers", add_split_file_option: Callable[[argparse.ArgumentParser], None]
) -> None:
    pool = actions.add_parser("pool", help="pool the top-k chunks of retrieval runs")
    add_database_url_option(pool)
    pool.add_argument("--index-version", required=True, help="chunk index the runs used")
    pool.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    add_split_file_option(pool)
    pool.add_argument(
        "--run", dest="runs", type=Path, action="append", required=True, help="TREC run file"
    )
    pool.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="top k per system (20)")
    pool.add_argument("--seed", type=int, default=POOL_SEED)
    pool.add_argument("--out", type=Path, default=DEFAULT_POOL)
    pool.add_argument(
        "--extend",
        type=Path,
        metavar="POOL",
        help="keep every chunk of this earlier pool that the index still has, and add the "
        "runs' top k as new (pending) items",
    )
    pool.set_defaults(run=_pool)

    label = actions.add_parser("label", help="label pooled chunks 0/1/2, blind")
    label.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    label.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    label.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    add_split_file_option(label)
    label.set_defaults(run=_label)

    qrels = actions.add_parser("qrels", help="export current labels as TREC qrels")
    qrels.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    qrels.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    qrels.add_argument("--out", type=Path, default=DEFAULT_QRELS)
    qrels.set_defaults(run=_qrels)


def _pool(args: argparse.Namespace) -> int:
    questions = load_questions(args.questions, read_split(args.split_file))
    hits = [hit for path in args.runs for hit in parse_run(Path(path).read_text("utf-8"))]
    entries = build_pool(questions, hits, depth=args.depth, seed=args.seed)
    previous: list[PoolItem] = []
    if args.extend is not None:
        if not Path(args.extend).is_file():
            print(f"error: no pool to extend at {args.extend}", file=sys.stderr)
            return 2
        previous = read_jsonl(args.extend, PoolItem)
    if (url := database_url_or_error(args)) is None:
        return 2
    refs = [e.chunk for e in entries] + [i.chunk for i in previous]
    with PostgresChunkText.connect(url) as source:
        texts = source.fetch(index_version=args.index_version, refs=refs)
    if args.extend is not None:
        fresh_count = len(entries)
        try:
            entries, dropped = extend_pool(
                previous, entries, questions, seed=args.seed, in_index=texts
            )
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        kept = len(previous) - len(dropped)
        print(
            f"extended {args.extend}: kept {kept} previously pooled chunks, "
            f"added {len(entries) - kept} new (of {fresh_count} in the runs' top "
            f"{args.depth}), dropped {len(dropped)} no longer in {args.index_version}"
        )
    try:
        items = attach_text(entries, texts, questions, index_version=args.index_version)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    write_jsonl(args.out, items)
    systems = sorted({h.system for h in hits})
    print(
        f"pooled {len(items)} chunks for {len(questions)} questions from {len(systems)} "
        f"systems ({', '.join(systems)}) at depth {args.depth}"
    )
    if len(systems) < PLANNED_SYSTEMS:
        print(
            f"warning: the plan pools {PLANNED_SYSTEMS} systems; got {len(systems)}",
            file=sys.stderr,
        )
    if len(questions) < TARGET_QUESTIONS:
        print(f"note: {len(questions)} questions so far; the plan asks for {TARGET_QUESTIONS}")
    empty = sorted({q.id for q in questions} - {i.qid for i in items})
    if empty:
        print(f"no chunk pooled for: {', '.join(empty)}")
    return 0


def _ask(prompt: str) -> str:
    print(prompt, end="", flush=True)
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line


def _label(args: argparse.Namespace) -> int:
    pool = read_jsonl(args.pool, PoolItem)
    questions = {q.id: q for q in load_questions(args.questions, read_split(args.split_file))}
    unknown = sorted({item.qid for item in pool} - set(questions))
    if unknown:
        print(f"error: pool has questions not in {args.questions}: {unknown}", file=sys.stderr)
        return 2
    labels_path: Path = args.labels
    result = label_session(
        pending_items(pool, read_jsonl(labels_path, Label)),
        questions,
        ask=_ask,
        show=print,
        save=lambda label: append_jsonl(labels_path, label),
        now=lambda: dt.datetime.now(dt.UTC),
    )
    left = len(pending_items(pool, read_jsonl(labels_path, Label)))
    print(f"\nlabelled {result.labelled}, skipped {result.skipped}, {left} pending")
    return 0


def _qrels(args: argparse.Namespace) -> int:
    pool = read_jsonl(args.pool, PoolItem)
    labels = read_jsonl(args.labels, Label)
    lines = qrels_lines(pool, labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(qrels_text(lines), "utf-8", newline="\n")
    pending = len(pending_items(pool, labels))
    print(f"wrote {args.out}: {len(lines)} labelled, {pending} pending")
    return 0
