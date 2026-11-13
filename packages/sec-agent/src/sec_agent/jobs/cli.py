"""`sec-agent jobs init|stats` and `sec-agent worker`."""

import argparse
import logging
import os
import socket
import sys
import uuid
from typing import TYPE_CHECKING, Any

import psycopg

from sec_agent.jobs.postgres import PostgresJobQueue
from sec_agent.jobs.registry import registered_handlers
from sec_agent.jobs.schema import apply_schema
from sec_agent.jobs.worker import Worker, WorkerConfig

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    jobs = subparsers.add_parser("jobs", help="manage the job queue")
    _add_database_url(jobs)
    jobs_commands = jobs.add_subparsers(dest="jobs_command", metavar="action", required=True)
    jobs_commands.add_parser("init", help="create the queue tables").set_defaults(run=_init)
    jobs_commands.add_parser("stats", help="jobs per status").set_defaults(run=_stats)

    worker = subparsers.add_parser("worker", help="run an ingest worker")
    _add_database_url(worker)
    worker.add_argument("--drain", action="store_true", help="exit when no job is ready")
    worker.add_argument("--lease", type=float, default=60.0, help="lease seconds (60)")
    worker.add_argument("--heartbeat", type=float, default=20.0, help="heartbeat seconds (20)")
    worker.add_argument("--poll", type=float, default=2.0, help="idle poll seconds (2)")
    worker.set_defaults(run=_worker)


def _add_database_url(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres connection string (default: $DATABASE_URL)",
    )


def _database_url(args: argparse.Namespace) -> str | None:
    url: str | None = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("error: set DATABASE_URL or pass --database-url", file=sys.stderr)
    return url


def _init(args: argparse.Namespace) -> int:
    if (url := _database_url(args)) is None:
        return 2
    conn: psycopg.Connection[Any]
    with psycopg.connect(url, autocommit=True) as conn:
        apply_schema(conn)
    print("jobs schema ready")
    return 0


def _stats(args: argparse.Namespace) -> int:
    if (url := _database_url(args)) is None:
        return 2
    with PostgresJobQueue.connect(url) as queue:
        for status, count in queue.counts().items():
            print(f"{status} {count}")
    return 0


def _worker(args: argparse.Namespace) -> int:
    handlers = registered_handlers()
    if not handlers:
        print("error: no job handlers are registered yet", file=sys.stderr)
        return 2
    if (url := _database_url(args)) is None:
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = WorkerConfig(
        owner=f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}",
        lease_seconds=args.lease,
        heartbeat_seconds=args.heartbeat,
        poll_seconds=args.poll,
    )
    with PostgresJobQueue.connect(url) as queue:
        try:
            processed = Worker(queue, handlers, config).run(drain=args.drain)
        except KeyboardInterrupt:
            return 130
    print(f"processed {processed} jobs")
    return 0
