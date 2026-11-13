"""`sec-agent mcp`: serve the five tools over stdio. Stdout is the protocol; notes go to stderr."""

import argparse
import sys
from typing import TYPE_CHECKING

import anyio

from sec_agent.jobs.cli import add_database_url_option, database_url_or_error
from sec_agent.mcp_server.contexts import EmbedderFactory, ServeConfigError, open_contexts
from sec_agent.mcp_server.server import build_server, serve_stdio
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.errors import EmbedderUnavailableError
from sec_agent.retrieval.models import EmbedderSpec
from sec_agent.retrieval.snapshot import SERVING

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]


def add_commands(subparsers: "Subparsers") -> None:
    mcp = subparsers.add_parser("mcp", help="serve the five tools to MCP clients over stdio")
    add_database_url_option(mcp)
    mcp.add_argument(
        "--facts-version", required=True, help="facts index version to answer from, e.g. v1"
    )
    mcp.add_argument(
        "--snapshot", default=None, help=f"text snapshot (default: the {SERVING} one, if any)"
    )
    mcp.add_argument("--lexical", action="store_true", help="search with BM25 only, no model")
    mcp.add_argument("--device", default=None, help="torch device for the query embedder")
    mcp.set_defaults(run=_serve)


def _serve(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    factory = _no_embedder if args.lexical else _model_embedder(args.device)
    try:
        with open_contexts(
            url, facts_version=args.facts_version, snapshot=args.snapshot, embedder=factory
        ) as contexts:
            if contexts.text is None:
                print(
                    f"note: no {SERVING} text snapshot; search_filings and diff_risk_factors"
                    " are off",
                    file=sys.stderr,
                )
            anyio.run(serve_stdio, build_server(contexts))
    except ServeConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _no_embedder(spec: EmbedderSpec) -> Embedder | None:
    return None


def _model_embedder(device: str | None) -> EmbedderFactory:
    def load(spec: EmbedderSpec) -> Embedder | None:
        from sec_agent.retrieval.sentence_transformer import SentenceTransformerEmbedder

        try:
            return SentenceTransformerEmbedder(spec, device=device)
        except EmbedderUnavailableError as error:
            print(f"note: {error}; search_filings runs on BM25 alone", file=sys.stderr)
            return None

    return load
