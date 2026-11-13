"""Create the LLM usage table. Safe to run from many replicas at once."""

from importlib.resources import files
from typing import Any

import psycopg

_SCHEMA_LOCK = 0x5EC0_0006  # advisory lock id; earlier schemas use 0x5EC0_0001..0x5EC0_0005


def schema_sql() -> str:
    return files("sec_agent.llm").joinpath("schema.sql").read_text("utf-8")


def apply_schema(conn: psycopg.Connection[Any]) -> None:
    """Apply `schema.sql` in one transaction, under an advisory lock."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK,))
        conn.execute(schema_sql().encode())
