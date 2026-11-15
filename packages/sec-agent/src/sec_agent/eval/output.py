"""What the eval commands share: `--record` into runs.csv, the commit measured, tables."""

import argparse
import datetime as dt
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from sec_agent.runs import RunRow, append_run


def add_record_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--record", type=Path, default=None, help="append the rows to runs.csv")
    parser.add_argument("--git-sha", default=None, help="commit measured (default: git HEAD)")


def record_rows(args: argparse.Namespace, build: Callable[[dt.date, str], list[RunRow]]) -> int:
    """Append the rows to `--record` when given; 2 when the commit cannot be named."""
    if args.record is None:
        return 0
    sha: str | None = args.git_sha or head_sha()
    if sha is None:
        print("error: --record needs --git-sha outside a git checkout", file=sys.stderr)
        return 2
    rows = build(dt.date.today(), sha)
    for row in rows:
        append_run(args.record, row)
    print(f"recorded {len(rows)} rows in {args.record}")
    return 0


def head_sha() -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip() or None


def table(rows: Sequence[Sequence[str]]) -> list[str]:
    """Rows as left-aligned columns two spaces apart."""
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return ["  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip() for r in rows]
