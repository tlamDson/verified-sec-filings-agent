"""`sec-agent` command line entry point. Subcommands (eval, ingest, ...) attach here."""

import argparse
from collections.abc import Sequence

from sec_agent import __version__
from sec_agent.filings import cli as filings_cli
from sec_agent.golden import cli as golden_cli
from sec_agent.jobs import cli as jobs_cli
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
    golden_cli.add_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    code: int = args.run(args)
    return code
