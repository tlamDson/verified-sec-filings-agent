"""`sec-agent api init|cohorts|serve`: create the API's tables, show activity per cohort
(real and simulated side by side), or serve the API over HTTP."""

import argparse
import datetime as dt
import os
import sys
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

import psycopg
import uvicorn

from sec_agent.agent.checkpoint import postgres_checkpointer
from sec_agent.agent.service import Agent
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.api.app import ApiDeps, create_app
from sec_agent.api.cohort_table import cohort_lines
from sec_agent.api.config import ApiConfig, ApiConfigError, config_from_env
from sec_agent.api.schema import apply_schema
from sec_agent.api.store_postgres import PostgresApiStore
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error
from sec_agent.llm.config import build_providers, providers_from_env
from sec_agent.llm.errors import LLMConfigError
from sec_agent.llm.openai_compat import OpenAICompatProvider
from sec_agent.llm.quota_postgres import PostgresQuotaStore
from sec_agent.llm.router import LLMRouter
from sec_agent.mcp_server.cli import model_embedder, no_embedder
from sec_agent.mcp_server.contexts import ServeConfigError, open_contexts
from sec_agent.retrieval.snapshot import SERVING

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    api = subparsers.add_parser("api", help="the HTTP API the web app calls")
    add_database_url_option(api)
    commands = api.add_subparsers(dest="api_command", metavar="action", required=True)
    commands.add_parser("init", help="create the usage, turn and feedback tables").set_defaults(
        run=_init
    )

    cohorts = commands.add_parser(
        "cohorts", help="activity per cohort, real and simulated side by side (U1)"
    )
    cohorts.add_argument("--from", dest="first", type=dt.date.fromisoformat, required=True)
    cohorts.add_argument("--to", dest="last", type=dt.date.fromisoformat, required=True)
    cohorts.set_defaults(run=_cohorts)

    serve = commands.add_parser(
        "serve", help="serve the API (run `agent init` and `api init` first)"
    )
    serve.add_argument(
        "--facts-version", required=True, help="facts index version to answer from, e.g. v1"
    )
    serve.add_argument(
        "--snapshot", default=None, help=f"text snapshot (default: the {SERVING} one, if any)"
    )
    serve.add_argument("--lexical", action="store_true", help="search with BM25 only, no model")
    serve.add_argument("--device", default=None, help="torch device for the query embedder")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (127.0.0.1)")
    serve.add_argument("--port", type=int, default=8000, help="port to listen on (8000)")
    serve.set_defaults(run=_serve)


def _init(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    conn: psycopg.Connection[Any]
    with psycopg.connect(url, autocommit=True) as conn:
        apply_schema(conn)
    print("api schema ready")
    return 0


def _cohorts(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    if args.first > args.last:
        print("error: --from is after --to", file=sys.stderr)
        return 2
    with PostgresApiStore.connect(url) as store:
        counts = store.cohort_counts(args.first, args.last)
    print(f"Turns asked {args.first.isoformat()} to {args.last.isoformat()} (UTC)")
    for line in cohort_lines(counts):
        print(line)
    return 0


def _serve(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    try:
        config = config_from_env(os.environ)
        providers = build_providers(providers_from_env(os.environ), os.environ)
    except (ApiConfigError, LLMConfigError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        _run(args, url, config, providers)
    except ServeConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _run(
    args: argparse.Namespace,
    url: str,
    config: ApiConfig,
    providers: tuple[OpenAICompatProvider, ...],
) -> None:
    """One replica: its own connections, pinned to one facts version and text snapshot."""
    embedder = no_embedder if args.lexical else model_embedder(args.device)
    with ExitStack() as stack:
        contexts = stack.enter_context(
            open_contexts(
                url, facts_version=args.facts_version, snapshot=args.snapshot, embedder=embedder
            )
        )
        if contexts.text is None:
            print(f"note: no {SERVING} text snapshot; the text tools are off", file=sys.stderr)
        tools = ToolRunner(contexts.facts, contexts.text)
        agent = Agent(
            router=LLMRouter(providers, quota=stack.enter_context(PostgresQuotaStore.connect(url))),
            tools=tools,
            checkpointer=stack.enter_context(postgres_checkpointer(url)),
        )
        deps = ApiDeps(
            agent=agent,
            tools=tools,
            companies=contexts.facts.companies,
            store=stack.enter_context(PostgresApiStore.connect(url)),
            config=config,
        )
        uvicorn.run(create_app(deps), host=args.host, port=args.port)
