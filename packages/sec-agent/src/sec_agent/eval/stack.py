"""What an eval night runs on: the product's router, tools and agent, pinned like a replica.

Providers come from `LLM_PROVIDERS` (default: the local llama.cpp server), through the
provider router with its quota in Postgres, so the cost cap and quotas hold as in the
product. Tools are pinned to one facts `index_version` and one text snapshot. The agent
keeps its conversations in memory: every eval item is a new conversation, and nothing of
an eval night is left in the product's checkpoint tables.
"""

import argparse
import os
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

from langgraph.checkpoint.memory import InMemorySaver

from sec_agent.agent.service import Agent
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.eval.chat import DEFAULT_MAX_TOKENS
from sec_agent.jobs.cli import add_database_url_option
from sec_agent.llm.config import build_providers, providers_from_env
from sec_agent.llm.quota_postgres import PostgresQuotaStore
from sec_agent.llm.router import LLMRouter
from sec_agent.mcp_server.cli import model_embedder, no_embedder
from sec_agent.mcp_server.contexts import open_contexts
from sec_agent.mcp_server.dispatch import ToolContexts
from sec_agent.rerank.serving import add_reranker_option, reranker_from_args
from sec_agent.retrieval.snapshot import SERVING


@dataclass(frozen=True)
class EvalStack:
    router: LLMRouter
    model: str
    """The providers in router order, e.g. "local:qwen3.6-35b-a3b"."""
    contexts: ToolContexts
    tools: ToolRunner
    agent: Agent


def add_stack_options(parser: argparse.ArgumentParser) -> None:
    add_database_url_option(parser)
    parser.add_argument("--facts-version", required=True, help="facts index version, e.g. v1")
    parser.add_argument(
        "--snapshot", default=None, help=f"text snapshot (default: the {SERVING} one, if any)"
    )
    parser.add_argument("--lexical", action="store_true", help="search with BM25 only, no model")
    parser.add_argument("--device", default=None, help="torch device for the query embedder")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    add_reranker_option(parser)


@contextmanager
def eval_stack(url: str, args: argparse.Namespace) -> Generator[EvalStack]:
    """Raises LLMConfigError, RerankerLoadError or ServeConfigError on a bad setup."""
    configs = providers_from_env(os.environ)
    providers = build_providers(configs, os.environ)
    reranker = reranker_from_args(args)
    with ExitStack() as stack:
        contexts = stack.enter_context(
            open_contexts(
                url,
                facts_version=args.facts_version,
                snapshot=args.snapshot,
                embedder=no_embedder if args.lexical else model_embedder(args.device),
                reranker=reranker,
            )
        )
        router = LLMRouter(providers, quota=stack.enter_context(PostgresQuotaStore.connect(url)))
        tools = ToolRunner(contexts.facts, contexts.text)
        yield EvalStack(
            router=router,
            model="+".join(f"{c.name}:{c.model}" for c in configs),
            contexts=contexts,
            tools=tools,
            agent=Agent(router=router, tools=tools, checkpointer=InMemorySaver()),
        )
