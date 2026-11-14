"""The `--reranker DIR` option of the API and MCP servers.

Without it (and without `SEC_RERANKER_DIR`), search runs without a reranker. A directory
that does not load is an error at start: a server never silently serves without the
reranker it was asked for. At query time, failures fall back to retrieval order instead.
"""

import argparse
import os
from collections.abc import Mapping
from pathlib import Path

from sec_agent.rerank.loader import RerankerLoadError, load_reranker
from sec_agent.rerank.service import RerankConfig, Reranker

RERANKER_ENV_VAR = "SEC_RERANKER_DIR"


def add_reranker_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--reranker",
        type=Path,
        default=None,
        help=f"exported ONNX reranker directory (default: ${RERANKER_ENV_VAR}, else none)",
    )
    parser.add_argument(
        "--rerank-timeout", type=float, default=RerankConfig().timeout_seconds, help="seconds"
    )


def reranker_from_args(
    args: argparse.Namespace, environ: Mapping[str, str] = os.environ
) -> Reranker | None:
    """Raises RerankerLoadError when the directory does not hold a valid reranker."""
    chosen: Path | None = args.reranker
    if chosen is None and (from_env := environ.get(RERANKER_ENV_VAR, "").strip()):
        chosen = Path(from_env)
    if chosen is None:
        return None
    try:
        config = RerankConfig(timeout_seconds=args.rerank_timeout)
    except ValueError as error:
        raise RerankerLoadError(str(error)) from error
    return Reranker(load_reranker(chosen).scorer, config)
