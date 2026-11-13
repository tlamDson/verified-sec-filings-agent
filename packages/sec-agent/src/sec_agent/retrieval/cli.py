"""`sec-agent index init|build|snapshot|verify|activate|search`."""

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg

from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.jobs.cli import add_database_url_option, database_url_or_error
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.errors import RetrievalError
from sec_agent.retrieval.models import Hit, SearchFilters, Snapshot
from sec_agent.retrieval.schema import apply_schema
from sec_agent.retrieval.snapshot import (
    SERVING,
    activate,
    create_snapshot,
    load_snapshot,
    serving_snapshot,
    verify_snapshot,
    write_manifest,
)
from sec_agent.retrieval.space import make_space
from sec_agent.retrieval.space_store import load_space

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

Conn = psycopg.Connection[Any]


def add_commands(subparsers: "Subparsers") -> None:
    index = subparsers.add_parser("index", help="build and query the hybrid retrieval index")
    add_database_url_option(index)
    actions = index.add_subparsers(dest="index_command", metavar="action", required=True)
    actions.add_parser("init", help="create the retrieval tables").set_defaults(run=_init)

    build = actions.add_parser("build", help="embed missing chunks, build HNSW and BM25 stats")
    _add_version_option(build)
    build.add_argument("--device", default=None, help="torch device, e.g. cuda or cpu")
    build.add_argument("--batch-size", type=int, default=64, help="chunks per batch (64)")
    build.set_defaults(run=_build)

    snapshot = actions.add_parser("snapshot", help="record a verified state of a space")
    snapshot.add_argument("name")
    _add_version_option(snapshot)
    snapshot.add_argument("--space", default=None, help="space name (default: default model)")
    snapshot.add_argument("--manifest", type=Path, default=None, help="also write it as JSON")
    snapshot.set_defaults(run=_snapshot)

    verify = actions.add_parser("verify", help="check a snapshot against the database")
    verify.add_argument("name")
    verify.set_defaults(run=_verify)

    act = actions.add_parser("activate", help="point a pointer at a verified snapshot")
    act.add_argument("name")
    act.add_argument("--pointer", default=SERVING, help=f"pointer name ({SERVING})")
    act.set_defaults(run=_activate)

    query = actions.add_parser("search", help="search a snapshot")
    query.add_argument("query")
    query.add_argument("--snapshot", default=None, help=f"snapshot (default: the {SERVING} one)")
    query.add_argument("--mode", choices=("hybrid", "dense", "lexical"), default="hybrid")
    query.add_argument("-k", type=int, default=10, help="results (10)")
    query.add_argument("--candidates", type=int, default=50, help="per arm, hybrid (50)")
    query.add_argument("--cik", action="append", default=[], help="repeatable")
    query.add_argument("--form", action="append", default=[], help="repeatable")
    query.add_argument("--section", action="append", default=[], help="repeatable")
    query.add_argument("--report-from", type=dt.date.fromisoformat, default=None)
    query.add_argument("--report-to", type=dt.date.fromisoformat, default=None)
    query.add_argument("--device", default=None, help="torch device for the query embedder")
    query.add_argument("--json", action="store_true", help="one JSON object per hit")
    query.set_defaults(run=_search)


def _add_version_option(parser: argparse.ArgumentParser) -> None:
    current = index_version(ChunkConfig())
    parser.add_argument(
        "--index-version", default=current, help=f"chunk build (this code: {current})"
    )


def _init(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        apply_schema(conn)
    print("retrieval schema ready")
    return 0


def _build(args: argparse.Namespace) -> int:
    from sec_agent.retrieval.build import build_index

    if (url := database_url_or_error(args)) is None:
        return 2
    try:
        embedder = _embedder(None, args.device)
        with psycopg.connect(url, autocommit=True) as conn:
            apply_schema(conn)
            report = build_index(conn, args.index_version, embedder, batch_size=args.batch_size)
    except RetrievalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(report.model_dump_json())
    return 0


def _snapshot(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            if args.space is None:
                from sec_agent.retrieval.sentence_transformer import DEFAULT_SPEC

                space = make_space(args.index_version, DEFAULT_SPEC)
            elif (space := load_space(conn, args.space)) is None:
                print(f"error: no embedding space named {args.space}", file=sys.stderr)
                return 1
            snapshot = create_snapshot(conn, args.name, space)
        except RetrievalError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    if args.manifest is not None:
        write_manifest(snapshot, args.manifest)
    print(snapshot.model_dump_json())
    return 0


def _verify(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            snapshot = load_snapshot(conn, args.name)
            verify_snapshot(conn, snapshot)
        except RetrievalError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    print(f"snapshot {snapshot.name} ok: {snapshot.chunk_count} chunks, {snapshot.content_sha256}")
    return 0


def _activate(args: argparse.Namespace) -> int:
    if (url := database_url_or_error(args)) is None:
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            activate(conn, args.name, args.pointer)
        except RetrievalError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    print(f"{args.pointer} -> {args.name}")
    return 0


def _search(args: argparse.Namespace) -> int:
    from sec_agent.retrieval.search import search

    if (url := database_url_or_error(args)) is None:
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            snapshot = (
                load_snapshot(conn, args.snapshot)
                if args.snapshot is not None
                else serving_snapshot(conn)
            )
            if snapshot is None:
                print(
                    f"error: no {SERVING} snapshot; run `sec-agent index activate NAME`"
                    " or pass --snapshot",
                    file=sys.stderr,
                )
                return 2
            filters = SearchFilters(
                ciks=tuple(args.cik),
                forms=tuple(args.form),
                sections=tuple(args.section),
                report_from=args.report_from,
                report_to=args.report_to,
            )
            embedder = None if args.mode == "lexical" else _embedder(snapshot, args.device)
            hits = search(
                conn,
                args.query,
                snapshot.embedding_space,
                embedder=embedder,
                mode=args.mode,
                filters=filters,
                k=args.k,
                candidates=args.candidates,
            )
        except (RetrievalError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    if not hits:
        print("no passages found")
    for hit in hits:
        print(hit.model_dump_json() if args.json else _line(hit))
    return 0


def _embedder(snapshot: Snapshot | None, device: str | None) -> Embedder:
    from sec_agent.retrieval.sentence_transformer import DEFAULT_SPEC, SentenceTransformerEmbedder

    spec = DEFAULT_SPEC if snapshot is None else snapshot.spec
    return SentenceTransformerEmbedder(spec, device=device)


def _line(hit: Hit) -> str:
    snippet = " ".join(hit.text.split())[:100]
    return (
        f"{hit.rank:>3} {hit.score:.4f} {hit.form:<6} {hit.report_date} CIK {hit.cik}"
        f" {hit.accession} {hit.section}#{hit.ordinal}  {snippet}"
    )
