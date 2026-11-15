"""`sec-agent golden split|gnum|public` (`pool|label|qrels` from `golden.gret.cli`, `gred`
from `golden.gred.cli`)."""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from sec_agent.golden.gnum.candidates import GNumCompany
from sec_agent.golden.gnum.generate import GNUM_SEED, SPLITS, GNumConfig, GNumResult, generate
from sec_agent.golden.gnum.source import PostgresFactSource
from sec_agent.golden.gred import cli as gred_cli
from sec_agent.golden.gret import cli as gret_cli
from sec_agent.golden.jsonl import write_jsonl
from sec_agent.golden.public.financebench import DOCUMENTS_FILE, QUESTIONS_FILE, load_g_public
from sec_agent.golden.public.manifest import DEFAULT_MANIFEST, NotVerifiedError, read_manifest
from sec_agent.golden.split import (
    DEFAULT_SPLIT_FILE,
    SPLIT_SEED,
    CompanySplitName,
    build_split,
    read_split,
    write_split,
)
from sec_agent.golden.universe import load_universe
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_GNUM_FILE = Path("data/golden/g_num.jsonl")
DEFAULT_PUBLIC_FILE = Path("data/golden/g_public.jsonl")


def add_split_file_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--split-file", type=Path, default=DEFAULT_SPLIT_FILE, help="company split JSON"
    )


def add_commands(subparsers: "Subparsers") -> None:
    golden = subparsers.add_parser("golden", help="golden sets for evaluation")
    actions = golden.add_subparsers(dest="golden_command", metavar="action", required=True)

    split = actions.add_parser("split", help="write the seeded company split")
    split.add_argument("--seed", type=int, default=SPLIT_SEED)
    split.add_argument("--out", type=Path, default=DEFAULT_SPLIT_FILE)
    split.set_defaults(run=_split)

    gnum = actions.add_parser("gnum", help="generate G-num questions from XBRL facts")
    add_database_url_option(gnum)
    gnum.add_argument("--index-version", required=True, help="facts snapshot to read")
    add_split_file_option(gnum)
    gnum.add_argument("--out", type=Path, default=DEFAULT_GNUM_FILE)
    gnum.add_argument("--seed", type=int, default=GNUM_SEED)
    gnum.add_argument("--totals", default=None, help="questions per split, e.g. test=300")
    gnum.set_defaults(run=_gnum)

    public = actions.add_parser("public", help="load FinanceBench once verified")
    public.add_argument("--questions", type=Path, required=True, help=QUESTIONS_FILE)
    public.add_argument("--documents", type=Path, required=True, help=DOCUMENTS_FILE)
    public.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    add_split_file_option(public)
    public.add_argument("--out", type=Path, default=DEFAULT_PUBLIC_FILE)
    public.set_defaults(run=_public)

    gret_cli.add_commands(actions, add_split_file_option)
    gred_cli.add_commands(actions)


def _split(args: argparse.Namespace) -> int:
    split = build_split(load_universe(), seed=args.seed)
    write_split(args.out, split)
    sizes = ", ".join(f"{name} {len(split.of(name))}" for name in SPLITS)
    print(f"wrote {args.out}: {sizes} (seed {split.seed})")
    return 0


def parse_totals(raw: str) -> dict[CompanySplitName, int]:
    """'train=900,dev=300,test=300' -> totals; splits left out ask nothing."""
    totals: dict[CompanySplitName, int] = {}
    for part in raw.split(","):
        name, sep, value = part.partition("=")
        if not sep or name.strip() not in SPLITS or not value.strip().isdigit():
            raise ValueError(f"bad totals entry {part!r}: want split=count")
        totals[cast(CompanySplitName, name.strip())] = int(value)
    return totals


def _gnum(args: argparse.Namespace) -> int:
    config = GNumConfig(seed=args.seed)
    if args.totals is not None:
        try:
            config = config.model_copy(update={"totals": parse_totals(args.totals)})
        except ValueError as error:
            print(f"error: --totals: {error}", file=sys.stderr)
            return 2
    if (url := database_url_or_error(args)) is None:
        return 2
    split = read_split(args.split_file)
    with PostgresFactSource.connect(url) as source:
        companies = [
            GNumCompany(
                company=c, facts=tuple(source.latest(index_version=args.index_version, cik=c.cik))
            )
            for c in split.companies
        ]
    result = generate(companies, config, args.index_version)
    write_jsonl(args.out, result.questions)
    _print_report(result, args.index_version)
    print(f"wrote {len(result.questions)} questions to {args.out}")
    return 0


def _print_report(result: GNumResult, index_version: str) -> None:
    print(f"{'split':<6} {'type':<16} {'candidates':>10} {'quota':>6} {'selected':>8}")
    for row in result.report:
        print(
            f"{row.split:<6} {row.qtype:<16} {row.candidates:>10} {row.quota:>6} {row.selected:>8}"
        )
    if result.companies_without_facts:
        print(f"no facts in {index_version} for: {', '.join(result.companies_without_facts)}")


def _public(args: argparse.Namespace) -> int:
    try:
        questions = load_g_public(
            args.questions,
            args.documents,
            read_manifest(args.manifest),
            read_split(args.split_file),
        )
    except NotVerifiedError as error:
        print(f"error: G-public is not verified, so it is not used: {error}", file=sys.stderr)
        return 2
    write_jsonl(args.out, questions)
    in_scope = sum(q.in_scope for q in questions)
    print(f"wrote {args.out}: {len(questions)} questions, {in_scope} in scope")
    return 0
