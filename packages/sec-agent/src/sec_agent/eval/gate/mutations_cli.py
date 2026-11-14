"""`sec-agent eval mutations`: G1, how many of the planted regressions the gate blocks.

Exit 0 only when every mutation is blocked by a gate finding (exit 1 of the gate).
"""

import argparse
import datetime as dt
import os
from pathlib import Path
from typing import TYPE_CHECKING

import sec_agent
from sec_agent.eval.gate.baseline import DEFAULT_BASELINE
from sec_agent.eval.gate.mutate import run_mutations, subprocess_gate
from sec_agent.eval.gate.mutations import MUTATIONS
from sec_agent.eval.output import add_record_options, record_rows
from sec_agent.runs import RunRow

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(actions: "Subparsers") -> None:
    mutations = actions.add_parser("mutations", help="G1: run the gate on 10 planted bugs")
    mutations.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    mutations.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    add_record_options(mutations)
    mutations.set_defaults(run=_mutations)


def _mutations(args: argparse.Namespace) -> int:
    repo = Path.cwd()
    package = Path(sec_agent.__file__).parent
    gate = subprocess_gate(repo, args.baseline.resolve())
    results = run_mutations(MUTATIONS, package, gate, workers=args.workers)
    for r in results:
        print(f"  {r.id} {r.outcome}: {r.detail}")
    blocked = sum(r.outcome == "blocked" for r in results)
    print(f"blocked {blocked}/{len(results)}")

    def rows(date: dt.date, sha: str) -> list[RunRow]:
        return [
            RunRow(
                date=date,
                git_sha=sha,
                metric="G1",
                system="eval-gate",
                split="none",
                cohort="none",
                n=len(results),
                value=blocked / len(results),
                unit="fraction",
                config="sec-agent eval gate over committed results",
                notes=f"blocked {blocked}/{len(results)} planted mutations",
            )
        ]

    code = record_rows(args, rows)
    return 1 if blocked < len(results) else code
