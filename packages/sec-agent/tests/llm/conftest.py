"""Fixtures for the LLM router tests: the usage table in the throwaway Postgres."""

import psycopg
import pytest

from sec_agent.llm.schema import apply_schema


@pytest.fixture
def llm_db(pg_uri: str) -> str:
    """The test database with the LLM usage table applied and empty."""
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE llm_usage")
    return pg_uri
