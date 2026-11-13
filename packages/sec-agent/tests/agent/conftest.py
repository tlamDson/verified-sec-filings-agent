"""Fixtures for the agent tests: recorded facts for the tools, and Postgres for checkpoints.

Facts come from the recorded companyfacts fixtures of Apple and NVIDIA, so tool values are
what SEC reported. The model is simulated (`llm_fakes.ScriptedProvider`), and so is the
filing text (`retrieval_corpus`).
"""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from tools_data import FACTS_VERSION
from xbrl_docs import APPLE, NVIDIA

from sec_agent.agent.checkpoint import FencedPostgresSaver, postgres_checkpointer
from sec_agent.retrieval.schema import apply_schema as apply_retrieval_schema
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize
from sec_agent.xbrl.schema import apply_schema as apply_facts_schema


@pytest.fixture(scope="session")
def memory_query() -> MemoryFactQuery:
    facts = [
        fact
        for document in (APPLE, NVIDIA)
        for fact in normalize(parse_companyfacts(document.read_bytes())).facts
    ]
    return MemoryFactQuery.from_facts(FACTS_VERSION, facts)


@pytest.fixture(scope="session")
def facts_ctx(memory_query: MemoryFactQuery) -> FactsContext:
    return FactsContext(
        companies=CompanyDirectory.from_universe(), facts=memory_query, index_version=FACTS_VERSION
    )


@pytest.fixture
def text_conn(pg_uri: str) -> Iterator[psycopg.Connection[Any]]:
    """Chunk, retrieval and facts schemas applied, every table they own empty."""
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_retrieval_schema(conn)
        apply_facts_schema(conn)
        conn.execute(
            "TRUNCATE indexed_filings, embedding_spaces, lexical_stats, lexical_df,"
            " facts, xbrl_ingests CASCADE"
        )
        yield conn


@pytest.fixture
def checkpoint_db(pg_uri: str) -> str:
    """The test database with the checkpoint tables set up and empty."""
    with postgres_checkpointer(pg_uri) as saver:
        saver.setup()
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        conn.execute("TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes")
    return pg_uri


@pytest.fixture
def replica_a(checkpoint_db: str) -> Iterator[FencedPostgresSaver]:
    """One API replica's checkpointer: its own connection to the shared database."""
    with postgres_checkpointer(checkpoint_db) as saver:
        yield saver


@pytest.fixture
def replica_b(checkpoint_db: str) -> Iterator[FencedPostgresSaver]:
    with postgres_checkpointer(checkpoint_db) as saver:
        yield saver
