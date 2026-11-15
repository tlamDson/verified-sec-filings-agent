"""Fixtures for the deterministic tools: the recorded Apple and NVIDIA facts, and Postgres.

The facts come from the recorded companyfacts fixtures (`tests/fixtures/companyfacts`), so
the values are what SEC reported. Filing text is simulated (`tests/fixtures/filings`).
"""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from tools_data import APPLE_CIK, FACTS_VERSION, NVIDIA_CIK
from xbrl_docs import APPLE, NVIDIA

from sec_agent.retrieval.schema import apply_schema as apply_retrieval_schema
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.models import Fact
from sec_agent.xbrl.normalize import normalize
from sec_agent.xbrl.schema import apply_schema as apply_facts_schema


@pytest.fixture(scope="session")
def recorded_facts() -> dict[int, list[Fact]]:
    """Every normalised fact version of Apple and NVIDIA, by CIK."""
    return {
        APPLE_CIK: normalize(parse_companyfacts(APPLE.read_bytes())).facts,
        NVIDIA_CIK: normalize(parse_companyfacts(NVIDIA.read_bytes())).facts,
    }


@pytest.fixture(scope="session")
def directory() -> CompanyDirectory:
    return CompanyDirectory.from_universe()


@pytest.fixture(scope="session")
def memory_query(recorded_facts: dict[int, list[Fact]]) -> MemoryFactQuery:
    facts = [f for versions in recorded_facts.values() for f in versions]
    return MemoryFactQuery.from_facts(FACTS_VERSION, facts)


@pytest.fixture(scope="session")
def facts_ctx(directory: CompanyDirectory, memory_query: MemoryFactQuery) -> FactsContext:
    return FactsContext(companies=directory, facts=memory_query, index_version=FACTS_VERSION)


@pytest.fixture
def tools_db(pg_uri: str) -> str:
    """Chunk, retrieval and facts schemas applied, every table they own empty."""
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_retrieval_schema(conn)
        apply_facts_schema(conn)
        conn.execute(
            "TRUNCATE indexed_filings, embedding_spaces, lexical_stats, lexical_df,"
            " facts, xbrl_ingests CASCADE"
        )
    return pg_uri


@pytest.fixture
def tools_conn(tools_db: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(tools_db, autocommit=True) as connection:
        yield connection
