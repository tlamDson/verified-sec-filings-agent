"""`sec-agent eval safety run|score`: S1 on G-red, with and without guardrails.

`run` drives each system over the items through the repository's LLM router (providers
from `LLM_PROVIDERS`, default the local llama.cpp server) and appends records to
`OUT_DIR/SYSTEM.jsonl`; it resumes where it stopped. `score` prints the rates and, with
`--record`, appends them to runs.csv.
"""

import argparse
import datetime as dt
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import InMemorySaver

from sec_agent.agent.config import AgentConfig
from sec_agent.agent.service import Agent
from sec_agent.eval.output import add_record_options, record_rows, table
from sec_agent.eval.safety.facts import companyfacts_context
from sec_agent.eval.safety.planted import PlantedTools
from sec_agent.eval.safety.records import SafetyRecord
from sec_agent.eval.safety.report import Rate, safety_report, safety_rows
from sec_agent.eval.safety.runner import run_safety
from sec_agent.golden.gred.cli import DEFAULT_GRED_FILE
from sec_agent.golden.gred.models import RedItem
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.llm.config import build_providers, providers_from_env
from sec_agent.llm.errors import LLMConfigError
from sec_agent.llm.quota import MemoryQuotaStore
from sec_agent.llm.router import LLMRouter
from sec_agent.tools.context import FactsContext

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

DEFAULT_RESULTS = Path("results/safety")
SYSTEMS: dict[str, AgentConfig] = {
    "guarded": AgentConfig(),
    "none": AgentConfig(guardrails=None),
}


def add_commands(actions: "Subparsers") -> None:
    safety = actions.add_parser("safety", help="S1: guardrails on G-red")
    steps = safety.add_subparsers(dest="safety_command", metavar="step", required=True)

    run = steps.add_parser("run", help="run G-red items through each system")
    run.add_argument("--items", type=Path, default=DEFAULT_GRED_FILE)
    run.add_argument("--systems", default="guarded,none", help=f"of {', '.join(SYSTEMS)}")
    run.add_argument(
        "--companyfacts", type=Path, nargs="+", required=True, help="recorded companyfacts JSON"
    )
    run.add_argument("--facts-version", default="companyfacts-fixtures")
    run.add_argument("--asked-on", type=dt.date.fromisoformat, default=dt.date.today())
    run.add_argument("--limit", type=int, default=None, help="first N items only")
    run.add_argument("--out-dir", type=Path, default=DEFAULT_RESULTS)
    run.set_defaults(run=_run)

    score = steps.add_parser("score", help="S1 rates from the records")
    score.add_argument("--systems", default="guarded,none")
    score.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    score.add_argument("--config", default="", help="configuration string for runs.csv")
    score.add_argument("--notes", default="", help="notes for runs.csv")
    score.add_argument("--index-version", default="", help="facts version measured on")
    add_record_options(score)
    score.set_defaults(run=_score)


def _systems(raw: str) -> list[str] | None:
    names = [s.strip() for s in raw.split(",") if s.strip()]
    if unknown := [s for s in names if s not in SYSTEMS]:
        print(f"error: unknown system: {', '.join(unknown)}", file=sys.stderr)
        return None
    return names


def _run(args: argparse.Namespace) -> int:
    systems = _systems(args.systems)
    if systems is None:
        return 2
    try:
        providers = build_providers(providers_from_env(os.environ), os.environ)
    except LLMConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    items = read_jsonl(args.items, RedItem)[: args.limit]
    facts = companyfacts_context(args.companyfacts, index_version=args.facts_version)
    router = LLMRouter(providers, quota=MemoryQuotaStore())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for system in systems:

        def make(item: RedItem, config: AgentConfig = SYSTEMS[system]) -> Agent:
            return _agent(router, facts, item, config)

        out = args.out_dir / f"{system}.jsonl"
        ran = run_safety(
            items, make, system=system, out=out, asked_on=args.asked_on, progress=_tick
        )
        print(f"{system}: ran {ran} items into {out}")
    return 0


def _agent(router: LLMRouter, facts: FactsContext, item: RedItem, config: AgentConfig) -> Agent:
    return Agent(
        router=router,
        tools=PlantedTools(facts, item.passages, company=item.company),
        checkpointer=InMemorySaver(),
        config=config,
    )


def _tick(record: SafetyRecord) -> None:
    outcome = "refused" if record.refused else record.status
    if record.attack_succeeded:
        outcome += " ATTACK-SUCCEEDED"
    print(f"  {record.system} {record.item_id}: {outcome}", flush=True)


def _score(args: argparse.Namespace) -> int:
    systems = _systems(args.systems)
    if systems is None:
        return 2
    files = [args.results_dir / f"{s}.jsonl" for s in systems]
    if missing := [str(p) for p in files if not p.exists()]:
        print(f"error: no records file: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        reports = safety_report(r for path in files for r in read_jsonl(path, SafetyRecord))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    rows = [["system", "attack blocked", "direct", "advice", "indirect success", "false refusal"]]
    for report in reports:
        rows.append(
            [
                report.system,
                _shown(report.attack_block),
                _shown(report.direct_block),
                _shown(report.advice_block),
                _shown(report.indirect_success),
                _shown(report.false_refusal),
            ]
        )
    print("\n".join(table(rows)))
    return record_rows(
        args,
        lambda date, sha: safety_rows(
            reports,
            date=date,
            git_sha=sha,
            config=args.config,
            notes=args.notes,
            index_version=args.index_version,
        ),
    )


def _shown(rate: Rate | None) -> str:
    if rate is None:
        return "-"
    return f"{rate.k}/{rate.n} {rate.value:.3f} [{rate.ci_low:.3f}, {rate.ci_high:.3f}]"
