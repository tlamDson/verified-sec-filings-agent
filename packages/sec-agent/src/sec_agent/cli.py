"""`sec-agent` command line entry point. Subcommands (eval, ingest, ...) attach here.

Every command runs with the tracing the environment asks for (`observability.setup`).
"""

import argparse
import os
import sys
from collections.abc import Sequence

from sec_agent import __version__
from sec_agent.agent import cli as agent_cli
from sec_agent.api import cli as api_cli
from sec_agent.eval import cli as eval_cli
from sec_agent.filings import cli as filings_cli
from sec_agent.golden import cli as golden_cli
from sec_agent.jobs import cli as jobs_cli
from sec_agent.mcp_server import cli as mcp_cli
from sec_agent.observability import cli as traces_cli
from sec_agent.observability.setup import TracingConfigError, trace_settings_from_env, tracing
from sec_agent.rerank import cli as rerank_cli
from sec_agent.retrieval import cli as retrieval_cli
from sec_agent.simusers import cli as sim_cli
from sec_agent.xbrl import cli as xbrl_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sec-agent",
        description="Research agent over SEC filings with traceable numbers.",
    )
    parser.add_argument("--version", action="version", version=f"sec-agent {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    jobs_cli.add_commands(subparsers)
    filings_cli.add_commands(subparsers)
    xbrl_cli.add_commands(subparsers)
    retrieval_cli.add_commands(subparsers)
    golden_cli.add_commands(subparsers)
    agent_cli.add_commands(subparsers)
    api_cli.add_commands(subparsers)
    eval_cli.add_commands(subparsers)
    mcp_cli.add_commands(subparsers)
    traces_cli.add_commands(subparsers)
    sim_cli.add_commands(subparsers)
    rerank_cli.add_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        trace_settings_from_env(os.environ)
    except TracingConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    with tracing(os.environ):
        code: int = args.run(args)
    return code
