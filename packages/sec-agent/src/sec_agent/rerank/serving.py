"""The `--reranker DIR` option of the API and MCP servers.

Without it (and without `SEC_RERANKER_DIR`), search runs without a reranker. A directory
that does not load is an error at start: a server never silently serves without the
reranker it was asked for. At query time, failures fall back to retrieval order instead.
"""

import argparse
import dataclasses
import json
import os
from collections.abc import Mapping
from pathlib import Path

from sec_agent.rerank.loader import RerankerLoadError, file_sha256, load_reranker
from sec_agent.rerank.models import TOKENIZER_FILE
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
    return served_reranker(args, environ)[0]


def served_reranker(
    args: argparse.Namespace, environ: Mapping[str, str] = os.environ
) -> tuple[Reranker | None, str]:
    """The reranker and what identifies it by content, for cache keys: "none", or its
    manifest name, the SHA-256 of its ONNX model and tokenizer, and its settings. A new
    model at the same directory therefore gets a new identity. Raises RerankerLoadError."""
    chosen: Path | None = args.reranker
    if chosen is None and (from_env := environ.get(RERANKER_ENV_VAR, "").strip()):
        chosen = Path(from_env)
    if chosen is None:
        return None, "none"
    try:
        config = RerankConfig(timeout_seconds=args.rerank_timeout)
    except ValueError as error:
        raise RerankerLoadError(str(error)) from error
    loaded = load_reranker(chosen)
    identity = json.dumps(
        {
            "name": loaded.manifest.name,
            "onnx_sha256": loaded.manifest.onnx_sha256,
            "tokenizer_sha256": file_sha256(chosen / TOKENIZER_FILE),
            "max_length": loaded.manifest.max_length,
            "config": dataclasses.asdict(config),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return Reranker(loaded.scorer, config), identity
