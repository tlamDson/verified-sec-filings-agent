"""`sec-agent report sync [--check]`: README results block and resume bullets from runs.csv."""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.report.bullets import MissingRunError, render_bullets
from sec_agent.report.render import render_results
from sec_agent.report.splice import MarkersMissingError, splice_block
from sec_agent.runs import read_runs

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    report = subparsers.add_parser("report", help="README results and bullets from runs.csv")
    steps = report.add_subparsers(dest="report_command", metavar="step", required=True)
    sync = steps.add_parser("sync", help="write the README results block and docs/bullets.md")
    sync.add_argument("--runs", type=Path, default=Path("runs.csv"))
    sync.add_argument("--readme", type=Path, default=Path("README.md"))
    sync.add_argument("--bullets", type=Path, default=Path("docs/bullets.md"))
    sync.add_argument("--check", action="store_true", help="write nothing; exit 1 if stale")
    sync.set_defaults(run=_sync)


def _sync(args: argparse.Namespace) -> int:
    try:
        rows = read_runs(args.runs)
        readme_old = args.readme.read_text("utf-8")
        readme_new = splice_block(readme_old, render_results(rows))
        bullets_new = render_bullets(rows)
    except (OSError, ValueError, MarkersMissingError, MissingRunError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    bullets_old = args.bullets.read_text("utf-8") if args.bullets.exists() else ""
    if args.check:
        stale = [
            str(path)
            for path, old, new in (
                (args.readme, readme_old, readme_new),
                (args.bullets, bullets_old, bullets_new),
            )
            if old != new
        ]
        if stale:
            print(f"stale, run `sec-agent report sync`: {', '.join(stale)}", file=sys.stderr)
            return 1
        return 0
    args.readme.write_text(readme_new, "utf-8", newline="\n")
    args.bullets.parent.mkdir(parents=True, exist_ok=True)
    args.bullets.write_text(bullets_new, "utf-8", newline="\n")
    return 0
