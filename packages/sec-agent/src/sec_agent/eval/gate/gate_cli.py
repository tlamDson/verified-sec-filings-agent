"""`sec-agent eval gate [--update]`: re-score the committed results, compare with the baseline.

Exit 0 when nothing moved, 1 when the gate finds drift or a regression, 2 on an error.
"""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.eval.gate.baseline import DEFAULT_BASELINE, read_baseline, write_baseline
from sec_agent.eval.gate.compare import compare
from sec_agent.eval.gate.measure import measure

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(actions: "Subparsers") -> None:
    gate = actions.add_parser("gate", help="G1: CI gate over the committed results")
    gate.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    gate.add_argument("--root", type=Path, default=Path(), help="repository root")
    gate.add_argument(
        "--update", action="store_true", help="write the measurement as the new baseline"
    )
    gate.set_defaults(run=_gate)


def _gate(args: argparse.Namespace) -> int:
    try:
        current = measure(args.root)
        if args.update:
            write_baseline(args.baseline, current)
            print(f"gate baseline written: {args.baseline} ({len(current.metrics)} metrics)")
            return 0
        baseline = read_baseline(args.baseline)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    findings = compare(baseline, current)
    for f in findings:
        print(f"{f.kind} {f.metric}: {f.message}")
    if findings:
        print(f"gate failed: {len(findings)} of {len(baseline.metrics)} metrics")
        return 1
    print(f"gate passed: {len(baseline.metrics)} metrics")
    return 0
