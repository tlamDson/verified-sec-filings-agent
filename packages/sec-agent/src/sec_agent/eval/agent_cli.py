"""`sec-agent eval agent run|score`: A1 task success on the fixed scenarios.

`run --system agent|rag` plays every scenario and writes `results/agent/SPLIT/SYSTEM.jsonl`
(with its cache); `score` checks the transcripts (no model, no database) and with
`--record` appends the A1 rows to runs.csv.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.eval.agent.checks import FailureKind
from sec_agent.eval.agent.report import AgentReport, agent_report
from sec_agent.eval.agent.rows import agent_rows
from sec_agent.eval.agent.runner import run_scenarios
from sec_agent.eval.agent.scenarios import Transcript, read_scenarios
from sec_agent.eval.agent.systems import AgentScenarios, RagScenarios, tool_search
from sec_agent.eval.chat import RouterChatModel
from sec_agent.eval.numeric.agent_model import AgentUnavailableError
from sec_agent.eval.output import add_record_options, record_rows, table
from sec_agent.eval.stack import add_stack_options, eval_stack
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.jobs.cli import database_url_or_error
from sec_agent.llm.errors import AllProvidersFailedError, LLMConfigError
from sec_agent.mcp_server.contexts import ServeConfigError
from sec_agent.rerank.loader import RerankerLoadError

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_SCENARIOS = Path("data/golden/agent_scenarios.jsonl")
DEFAULT_RESULTS = Path("results/agent")
_FAILURES: tuple[FailureKind, ...] = (
    "status",
    "tool",
    "figure",
    "citation",
    "unfaithful",
    "says",
    "not_says",
)


def add_commands(actions: "Subparsers") -> None:
    agent = actions.add_parser("agent", help="A1: agent task success on fixed scenarios")
    commands = agent.add_subparsers(dest="agent_eval_command", metavar="action", required=True)

    run = commands.add_parser("run", help="play the scenarios with the agent or RAG only")
    run.add_argument("--system", choices=("agent", "rag"), required=True)
    _common(run)
    add_stack_options(run)
    run.set_defaults(run=_run)

    score = commands.add_parser("score", help="check the transcripts and report A1")
    score.add_argument("--systems", required=True, help="comma-separated, e.g. rag,agent")
    _common(score)
    score.add_argument("--index-version", default="", help="facts version the runs used")
    add_record_options(score)
    score.set_defaults(run=_score)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--split", choices=("train", "dev", "test"), default="test")
    parser.add_argument("--results-dir", type=Path, default=None)


def _results(args: argparse.Namespace) -> Path:
    return args.results_dir or DEFAULT_RESULTS / args.split


def _run(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    scenarios = [s for s in read_scenarios(args.scenarios) if s.split == args.split]
    results = _results(args) / f"{args.system}.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    try:
        with eval_stack(url, args) as stack:
            if args.system == "agent":
                system = AgentScenarios(
                    stack.agent,
                    model=f"agent:{stack.model}",
                    asked_on=stack.asked_on,
                    fingerprint=stack.fingerprint,
                )
                summary = run_scenarios(scenarios, system, results=results, now=_now)
            else:
                chat = RouterChatModel(stack.router, name=stack.model, max_tokens=args.max_tokens)
                rag = RagScenarios(tool_search(stack.tools), chat, asked_on=stack.asked_on)
                summary = run_scenarios(scenarios, rag, results=results, now=_now)
    except (LLMConfigError, RerankerLoadError, ServeConfigError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (AllProvidersFailedError, AgentUnavailableError) as error:
        print(f"stopped: {error}; rerun to resume from the cache", file=sys.stderr)
        return 1
    print(f"{args.system}: played {summary.asked}, cached {summary.cached}; wrote {results}")
    return 0


def _score(args: argparse.Namespace) -> int:
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    files = {s: _results(args) / f"{s}.jsonl" for s in systems}
    if missing := [str(path) for path in files.values() if not path.exists()]:
        print(f"error: no transcripts file: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        scenarios = [s for s in read_scenarios(args.scenarios) if s.split == args.split]
        report = agent_report(
            scenarios, {s: read_jsonl(path, Transcript) for s, path in files.items()}
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    _print(report, args.split)
    return record_rows(
        args,
        lambda date, sha: agent_rows(
            report, split=args.split, date=date, git_sha=sha, index_version=args.index_version
        ),
    )


def _print(report: AgentReport, split: str) -> None:
    print(f"A1 task success, split {split}: {report.scored} of {report.scenarios} scenarios scored")
    for system, count in report.missing.items():
        if count:
            print(f"note: {system} has no transcript for {count} scenarios; they are not scored")
    print("system, passed/n, rate, 95% Wilson interval, model:")
    rows = [
        [
            s.system,
            f"{s.passed}/{s.n}",
            f"{s.rate:.3f}",
            f"[{s.interval.low:.3f}, {s.interval.high:.3f}]",
            ",".join(s.models),
        ]
        for s in report.systems
    ]
    for line in table(rows):
        print(f"  {line}")
    for s in report.systems:
        failed = ", ".join(f"{k} {s.failures[k]}" for k in _FAILURES if k in s.failures) or "none"
        categories = ", ".join(f"{c} {p}/{n}" for c, (p, n) in s.by_category.items())
        print(f"  {s.system} failed checks: {failed}; by category: {categories}")
    for c in report.comparisons:
        r = c.result
        print(
            f"{c.system} vs {c.other}: {c.system} only {r.a_only}, {c.other} only {r.b_only},"
            f" exact McNemar p = {r.p_value:.4f}"
        )


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
