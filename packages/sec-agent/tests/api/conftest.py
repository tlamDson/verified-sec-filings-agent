"""Fixtures for the API tests: recorded facts for the tools, and Postgres for the API tables.

Facts come from the recorded companyfacts fixtures of Apple and NVIDIA, so tool values are
what SEC reported. The model is simulated (`llm_fakes.ScriptedProvider`).
"""

from collections.abc import Iterator

import psycopg
import pytest
from tools_data import FACTS_VERSION
from xbrl_docs import APPLE, NVIDIA

from sec_agent.api.schema import apply_schema
from sec_agent.api.store import ApiStore, MemoryApiStore
from sec_agent.api.store_postgres import PostgresApiStore
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize


@pytest.fixture(scope="session")
def facts_ctx() -> FactsContext:
    facts = [
        fact
        for document in (APPLE, NVIDIA)
        for fact in normalize(parse_companyfacts(document.read_bytes())).facts
    ]
    return FactsContext(
        companies=CompanyDirectory.from_universe(),
        facts=MemoryFactQuery.from_facts(FACTS_VERSION, facts),
        index_version=FACTS_VERSION,
    )


@pytest.fixture
def api_db(pg_uri: str) -> str:
    """The test database with the API tables created and empty."""
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE api_usage, api_turns, api_feedback")
    return pg_uri


@pytest.fixture(params=["memory", "postgres"])
def store(request: pytest.FixtureRequest) -> Iterator[ApiStore]:
    """Every store test runs on both implementations."""
    if request.param == "memory":
        yield MemoryApiStore()
        return
    with PostgresApiStore.connect(request.getfixturevalue("api_db")) as postgres:
        yield postgres
