"""The `--database-url` option shared by CLI commands, defaulting to $DATABASE_URL."""

import argparse
import os
import sys


def add_database_url(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres connection string (default: $DATABASE_URL)",
    )


def database_url(args: argparse.Namespace) -> str | None:
    """The URL from the flag or the environment; None (after printing why) when neither."""
    url: str | None = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("error: set DATABASE_URL or pass --database-url", file=sys.stderr)
    return url
