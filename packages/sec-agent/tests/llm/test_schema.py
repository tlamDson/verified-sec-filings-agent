"""The LLM usage table: created once, safe to apply again."""

import psycopg

from sec_agent.llm.schema import apply_schema


def test_schema_can_be_applied_twice(pg_uri: str) -> None:
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_schema(conn)
        apply_schema(conn)
        row = conn.execute("SELECT to_regclass('llm_usage')").fetchone()
    assert row is not None
    assert row[0] == "llm_usage"
