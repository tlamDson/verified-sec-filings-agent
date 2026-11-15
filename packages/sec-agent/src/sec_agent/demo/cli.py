"""`sec-agent demo build`: the static demo site from runs.csv and committed transcripts."""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.demo.page import render_page
from sec_agent.demo.samples import pick_samples
from sec_agent.eval.agent.scenarios import Transcript, read_scenarios
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.runs import read_runs

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    demo = subparsers.add_parser("demo", help="static public demo site")
    steps = demo.add_subparsers(dest="demo_command", metavar="step", required=True)
    build = steps.add_parser("build", help="write index.html from committed results")
    build.add_argument("--runs", type=Path, default=Path("runs.csv"))
    build.add_argument("--scenarios", type=Path, default=Path("data/golden/agent_scenarios.jsonl"))
    build.add_argument("--transcripts", type=Path, default=Path("results/agent/test/agent.jsonl"))
    build.add_argument("--out", type=Path, default=Path("site"))
    build.add_argument("--limit", type=int, default=10, help="sample answers to show")
    build.set_defaults(run=_build)


def _build(args: argparse.Namespace) -> int:
    missing = [p for p in (args.runs, args.scenarios, args.transcripts) if not p.is_file()]
    if missing:
        print(f"error: missing input: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2
    try:
        rows = read_runs(args.runs)
        scenarios = read_scenarios(args.scenarios)
        transcripts = read_jsonl(args.transcripts, Transcript)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    page = render_page(rows, pick_samples(scenarios, transcripts, limit=args.limit))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "index.html").write_text(page, "utf-8", newline="\n")
    (args.out / ".nojekyll").write_text("", "utf-8")
    return 0
