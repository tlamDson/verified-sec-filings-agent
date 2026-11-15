"""`sec-agent traces table SPANS.jsonl`: the L1 table from a span file, optionally recorded.

    sec-agent traces table spans.jsonl --record runs.csv --system b2 --split dev --cohort none

The spans come from a run with `SEC_AGENT_TRACE_FILE` set. Say which users made the
traffic with `--cohort`: traffic from simulated users is `simulated`, never `real`.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from sec_agent.eval.output import add_record_options, record_rows, table
from sec_agent.observability.latency import TraceReport, report_rows, trace_report
from sec_agent.observability.span_file import SpanFileError, read_spans
from sec_agent.runs import Cohort, RunRow, Split

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    traces = subparsers.add_parser("traces", help="read the spans of traced runs")
    commands = traces.add_subparsers(dest="traces_command", metavar="action", required=True)
    tabulate = commands.add_parser(
        "table", help="latency per step and tokens per question (L1) from a span file"
    )
    tabulate.add_argument("spans", type=Path, help="JSONL span file (SEC_AGENT_TRACE_FILE)")
    add_record_options(tabulate)
    tabulate.add_argument("--system", default=None, help="configuration measured, e.g. b2")
    tabulate.add_argument("--split", choices=get_args(Split), default=None)
    tabulate.add_argument(
        "--cohort",
        choices=get_args(Cohort),
        default=None,
        help="who asked: real users, simulated users, or none (an eval run)",
    )
    tabulate.add_argument("--index-version", default="")
    tabulate.add_argument("--config", default="")
    tabulate.add_argument("--notes", default="")
    tabulate.set_defaults(run=_table)


def _table(args: argparse.Namespace) -> int:
    if args.record is not None and None in (args.system, args.split, args.cohort):
        print("error: --record needs --system, --split and --cohort", file=sys.stderr)
        return 2
    try:
        report = trace_report(read_spans(args.spans))
    except (SpanFileError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for line in _lines(report):
        print(line)

    def build(date: dt.date, sha: str) -> list[RunRow]:
        return report_rows(
            report,
            date=date,
            git_sha=sha,
            system=args.system,
            split=args.split,
            cohort=args.cohort,
            index_version=args.index_version,
            config=args.config,
            notes=args.notes,
        )

    return record_rows(args, build)


def _lines(report: TraceReport) -> list[str]:
    steps = [["step", "n", "errors", "p50_ms", "p95_ms"]]
    steps += [
        [s.step, str(s.n), str(s.errors), f"{s.p50_ms:.1f}", f"{s.p95_ms:.1f}"]
        for s in report.steps
    ]
    lines = table(steps)
    if report.tokens:
        tokens = [["tokens", "questions", "mean", "p50", "p95"]]
        tokens += [
            [t.kind, str(t.n), f"{t.mean:.1f}", f"{t.p50:.1f}", f"{t.p95:.1f}"]
            for t in report.tokens
        ]
        lines += ["", *table(tokens)]
    return lines
