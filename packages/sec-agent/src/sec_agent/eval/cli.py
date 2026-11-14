"""`sec-agent eval numeric`, plus `eval answer` (`eval.answer_cli`), `eval agent run|score`
(`eval.agent_cli`) and `eval retrieval run|score` (`eval.retrieval_cli`)."""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from sec_agent.eval import agent_cli, answer_cli, retrieval_cli
from sec_agent.eval.numeric.grade import ErrorKind
from sec_agent.eval.numeric.report import NumericReport, SystemAccuracy, numeric_report
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.eval.output import add_record_options, record_rows, table
from sec_agent.eval.records import numeric_rows
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.jsonl import read_jsonl

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_GNUM_FILE = Path("data/golden/g_num.jsonl")
DEFAULT_RESULTS = Path("results/numeric")
_ERRORS: tuple[ErrorKind, ...] = get_args(ErrorKind)


def add_commands(subparsers: "Subparsers") -> None:
    evaluate = subparsers.add_parser("eval", help="score systems on the golden sets")
    actions = evaluate.add_subparsers(dest="eval_command", metavar="action", required=True)

    numeric = actions.add_parser("numeric", help="N1: grade answers to G-num questions")
    numeric.add_argument("--questions", type=Path, default=DEFAULT_GNUM_FILE)
    numeric.add_argument("--split", choices=("train", "dev", "test"), default="test")
    numeric.add_argument("--systems", required=True, help="comma-separated, e.g. b0,b1,b2")
    numeric.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help=f"holds SYSTEM.jsonl answer records (default: {DEFAULT_RESULTS}/SPLIT)",
    )
    add_record_options(numeric)
    numeric.set_defaults(run=_numeric)

    answer_cli.add_commands(actions)
    agent_cli.add_commands(actions)
    retrieval_cli.add_commands(actions)


def _numeric(args: argparse.Namespace) -> int:
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    results: Path = args.results_dir or DEFAULT_RESULTS / args.split
    files = {s: results / f"{s}.jsonl" for s in systems}
    if missing := [str(path) for path in files.values() if not path.exists()]:
        print(f"error: no answers file: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        questions = [q for q in read_jsonl(args.questions, NumQuestion) if q.split == args.split]
        report = numeric_report(
            questions, {s: read_jsonl(path, AnswerRecord) for s, path in files.items()}
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    _print(report, args.split)
    return record_rows(
        args, lambda date, sha: numeric_rows(report, split=args.split, date=date, git_sha=sha)
    )


def _print(report: NumericReport, split: str) -> None:
    print(
        f"N1 numeric accuracy, split {split}: {report.scored} of {report.questions} questions"
        f" scored (index {report.index_version})"
    )
    for system, count in report.missing.items():
        if count:
            print(f"note: {system} has no answer for {count} questions; they are not scored")
    print("system, correct/n, accuracy, 95% Wilson interval, model:")
    for line in table([_row(s) for s in report.systems]):
        print(f"  {line}")
    for s in report.systems:
        errors = ", ".join(f"{e} {s.errors[e]}" for e in _ERRORS if e in s.errors) or "none"
        types = ", ".join(f"{t} {c}/{n}" for t, (c, n) in s.by_qtype.items())
        print(f"  {s.system} errors: {errors}; by type: {types}")
    for c in report.comparisons:
        r = c.result
        print(
            f"{c.system} vs {c.other}: {c.system} only {r.a_only}, {c.other} only {r.b_only},"
            f" exact McNemar p = {r.p_value:.4f}"
        )


def _row(s: SystemAccuracy) -> list[str]:
    return [
        s.system,
        f"{s.correct}/{s.n}",
        f"{s.accuracy:.3f}",
        f"[{s.interval.low:.3f}, {s.interval.high:.3f}]",
        ",".join(s.models),
    ]
