"""`sec-agent xbrl init|enqueue`: create the facts tables, queue companyfacts ingests."""

import argparse
import sys
from typing import TYPE_CHECKING, Any

import psycopg

from sec_agent.database_url import add_database_url, database_url
from sec_agent.jobs.models import NewJob
from sec_agent.jobs.postgres import PostgresJobQueue
from sec_agent.xbrl.ingest import companyfacts_job
from sec_agent.xbrl.schema import apply_schema

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    xbrl = subparsers.add_parser("xbrl", help="XBRL facts")
    add_database_url(xbrl)
    actions = xbrl.add_subparsers(dest="xbrl_command", metavar="action", required=True)
    actions.add_parser("init", help="create the facts tables").set_defaults(run=_init)
    enqueue = actions.add_parser("enqueue", help="queue one companyfacts ingest per CIK")
    enqueue.add_argument("--index-version", required=True, help="snapshot to write, e.g. v1")
    enqueue.add_argument("--refresh", action="store_true", help="bypass the raw cache")
    enqueue.add_argument("ciks", nargs="+", metavar="CIK")
    enqueue.set_defaults(run=_enqueue)


def _init(args: argparse.Namespace) -> int:
    if (url := database_url(args)) is None:
        return 2
    conn: psycopg.Connection[Any]
    with psycopg.connect(url, autocommit=True) as conn:
        apply_schema(conn)
    print("facts schema ready")
    return 0


def _enqueue(args: argparse.Namespace) -> int:
    try:
        jobs: list[NewJob] = [
            companyfacts_job(cik, args.index_version, refresh=args.refresh) for cik in args.ciks
        ]
    except ValueError as error:
        print(f"error: bad CIK or index version: {error}", file=sys.stderr)
        return 2
    if (url := database_url(args)) is None:
        return 2
    with PostgresJobQueue.connect(url) as queue:
        inserted = queue.enqueue(jobs)
    print(f"enqueued {inserted} of {len(jobs)} (the rest were already queued)")
    return 0
