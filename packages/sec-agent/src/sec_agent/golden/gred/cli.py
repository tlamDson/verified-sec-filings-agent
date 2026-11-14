"""`sec-agent golden gred`: write the G-red set (synthetic prompts, simulated passages)."""

import argparse
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from sec_agent.golden.gred.generate import DEFAULT_SEED, generate_gred
from sec_agent.golden.jsonl import write_jsonl

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_GRED_FILE = Path("data/golden/g_red.jsonl")


def add_commands(actions: "Subparsers") -> None:
    gred = actions.add_parser("gred", help="write G-red, the S1 safety set")
    gred.add_argument("--seed", type=int, default=DEFAULT_SEED)
    gred.add_argument("--out", type=Path, default=DEFAULT_GRED_FILE)
    gred.set_defaults(run=_gred)


def _gred(args: argparse.Namespace) -> int:
    items = generate_gred(args.seed)
    write_jsonl(args.out, items)
    kinds = Counter(item.kind for item in items)
    print(f"wrote {args.out}: " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    return 0
