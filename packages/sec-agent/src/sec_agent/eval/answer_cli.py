"""`sec-agent eval answer --system b0|b1|b2`: ask one system the G-num questions of a split.

Answers go to `results/numeric/SPLIT/SYSTEM.jsonl` (and its cache), which `eval numeric`
then grades. An interrupted night resumes from the cache; `--limit` asks only the first N
questions in file order, so a short night is reported with its true N, never padded.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.eval.chat import RouterChatModel
from sec_agent.eval.numeric.agent_model import AgentChatModel, AgentUnavailableError
from sec_agent.eval.numeric.baselines import B0, B1, B2, ChatModel, NumericSystem
from sec_agent.eval.numeric.passages import SearchPassages
from sec_agent.eval.numeric.runner import run_numeric
from sec_agent.eval.stack import EvalStack, add_stack_options, eval_stack
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.jobs.cli import database_url_or_error
from sec_agent.llm.errors import AllProvidersFailedError, LLMConfigError
from sec_agent.mcp_server.contexts import ServeConfigError
from sec_agent.rerank.loader import RerankerLoadError

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_GNUM_FILE = Path("data/golden/g_num.jsonl")
DEFAULT_RESULTS = Path("results/numeric")


def add_commands(actions: "Subparsers") -> None:
    answer = actions.add_parser("answer", help="N1: ask b0, b1 or b2 the G-num questions")
    answer.add_argument("--system", choices=("b0", "b1", "b2"), required=True)
    answer.add_argument("--questions", type=Path, default=DEFAULT_GNUM_FILE)
    answer.add_argument("--split", choices=("train", "dev", "test"), default="test")
    answer.add_argument("--limit", type=int, default=None, help="ask only the first N questions")
    answer.add_argument("--results-dir", type=Path, default=None)
    answer.add_argument(
        "--asked-on", type=dt.date.fromisoformat, default=None, help="b2's date (default today)"
    )
    add_stack_options(answer)
    answer.set_defaults(run=_answer)


def _answer(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    questions = [q for q in read_jsonl(args.questions, NumQuestion) if q.split == args.split]
    if args.limit is not None:
        questions = questions[: args.limit]
    if not questions:
        print(f"error: no {args.split} question in {args.questions}", file=sys.stderr)
        return 2
    results: Path = (args.results_dir or DEFAULT_RESULTS / args.split) / f"{args.system}.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    try:
        with eval_stack(url, args) as stack:
            system, model = _system(args, stack)
            summary = run_numeric(
                questions, system, model, results=results, now=lambda: dt.datetime.now(dt.UTC)
            )
    except (LLMConfigError, RerankerLoadError, ServeConfigError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (AllProvidersFailedError, AgentUnavailableError) as error:
        print(f"stopped: {error}; rerun to resume from the cache", file=sys.stderr)
        return 1
    print(f"{system.name}: asked {summary.asked}, cached {summary.cached}; wrote {results}")
    return 0


def _system(args: argparse.Namespace, stack: EvalStack) -> tuple[NumericSystem, ChatModel]:
    chat = RouterChatModel(stack.router, name=stack.model, max_tokens=args.max_tokens)
    if args.system == "b0":
        return B0(), chat
    if args.system == "b1":
        text = stack.contexts.text
        if text is None:
            raise ValueError("b1 needs a text snapshot; none is pinned")
        return B1(SearchPassages(text.conn, text.space, text.embedder)), chat
    asked_on: dt.date = args.asked_on or dt.date.today()
    return B2(), AgentChatModel(stack.agent, name=f"agent:{stack.model}", asked_on=asked_on)
