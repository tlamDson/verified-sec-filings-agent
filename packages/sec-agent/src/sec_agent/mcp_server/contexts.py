"""What the MCP server reads, pinned at start: one facts `index_version`, one text snapshot.

The text snapshot is the named one, or the serving pointer's; with neither, only the three
numeric tools answer and the text tools say no index is loaded. A facts version that holds
no facts is refused at start, since every lookup would come back "not reported" (E12).
"""

from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from typing import Any

import psycopg

from sec_agent.mcp_server.dispatch import ToolContexts
from sec_agent.rerank.service import Reranker
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.errors import SnapshotNotFoundError
from sec_agent.retrieval.models import EmbedderSpec, Snapshot
from sec_agent.retrieval.snapshot import SERVING, load_snapshot, serving_snapshot
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext, TextContext
from sec_agent.tools.risk_sections import PostgresRiskSections
from sec_agent.xbrl.store import PostgresFactStore

EmbedderFactory = Callable[[EmbedderSpec], Embedder | None]
"""The query embedder for a snapshot's model; None searches with BM25 alone."""

_HAS_FACTS = b"SELECT EXISTS (SELECT 1 FROM facts WHERE index_version = %s)"


class ServeConfigError(Exception):
    """The server cannot start on what it was asked to serve."""


@contextmanager
def open_contexts(
    conninfo: str,
    *,
    facts_version: str,
    embedder: EmbedderFactory,
    snapshot: str | None = None,
    companies: CompanyDirectory | None = None,
    reranker: Reranker | None = None,
) -> Generator[ToolContexts]:
    directory = CompanyDirectory.from_universe() if companies is None else companies
    with ExitStack() as stack:
        store = stack.enter_context(PostgresFactStore.connect(conninfo))
        conn = stack.enter_context(psycopg.connect(conninfo, autocommit=True))
        row = conn.execute(_HAS_FACTS, (facts_version,)).fetchone()
        if row is None or not row[0]:
            raise ServeConfigError(f"facts index version {facts_version!r} holds no facts")
        facts = FactsContext(companies=directory, facts=store, index_version=facts_version)
        pinned = _snapshot(conn, snapshot)
        text = (
            None
            if pinned is None
            else TextContext(
                companies=directory,
                conn=conn,
                space=pinned.embedding_space,
                sections=PostgresRiskSections(conn),
                facts_version=facts_version,
                embedder=embedder(pinned.spec),
                reranker=reranker,
            )
        )
        yield ToolContexts(facts=facts, text=text)


def _snapshot(conn: psycopg.Connection[Any], name: str | None) -> Snapshot | None:
    if name is None:
        return serving_snapshot(conn, SERVING)
    try:
        return load_snapshot(conn, name)
    except SnapshotNotFoundError as error:
        raise ServeConfigError(f"no text snapshot named {name!r}") from error
