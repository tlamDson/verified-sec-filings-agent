"""`sec-agent filings init|enqueue`."""

import argparse
import datetime as dt
import sys
from typing import TYPE_CHECKING

from pydantic import ValidationError

from sec_agent.edgar.client import EdgarClient
from sec_agent.edgar.errors import EdgarConfigError
from sec_agent.filings.enqueue import enqueue_filings
from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.store import PostgresChunkStore
from sec_agent.filings.submissions import DEFAULT_WINDOW, ReportWindow
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error
from sec_agent.jobs.postgres import PostgresJobQueue

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    filings = subparsers.add_parser("filings", help="build the filing text index")
    add_database_url_option(filings)
    actions = filings.add_subparsers(dest="filings_command", metavar="action", required=True)
    actions.add_parser("init", help="create the chunk tables").set_defaults(run=_init)

    enqueue = actions.add_parser(
        "enqueue", help="enqueue one filing.sections job per 10-K/10-Q of each company"
    )
    enqueue.add_argument("ciks", nargs="+", metavar="CIK")
    enqueue.add_argument(
        "--report-from",
        type=dt.date.fromisoformat,
        default=DEFAULT_WINDOW.start,
        help=f"first period of report, YYYY-MM-DD ({DEFAULT_WINDOW.start})",
    )
    enqueue.add_argument(
        "--report-to",
        type=dt.date.fromisoformat,
        default=DEFAULT_WINDOW.end,
        help=f"last period of report, YYYY-MM-DD ({DEFAULT_WINDOW.end})",
    )
    enqueue.set_defaults(run=_enqueue)


def _init(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    with PostgresChunkStore.connect(url) as store:
        store.apply_schema()
    print(f"chunk schema ready; this code builds index version {index_version(ChunkConfig())}")
    return 0


def _enqueue(args: argparse.Namespace) -> int:
    try:
        window = ReportWindow(start=args.report_from, end=args.report_to)
    except ValidationError:
        print("error: --report-from must not be after --report-to", file=sys.stderr)
        return 2
    if (url := database_url_or_error(args)) is None:
        return 2
    version = index_version(ChunkConfig())
    try:
        client = EdgarClient.from_env()
    except EdgarConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    with client, PostgresJobQueue.connect(url) as queue:
        for cik in args.ciks:
            found, added = enqueue_filings(client.get_json, queue, cik, window, version)
            print(f"CIK {cik}: {found} filings, {added} new jobs for {version}")
    return 0
