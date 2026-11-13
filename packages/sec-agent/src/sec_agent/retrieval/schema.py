"""Create the retrieval tables (and the chunk tables they reference). Safe to run concurrently."""

from importlib.resources import files
from typing import Any

import psycopg

from sec_agent.filings.store import apply_schema as apply_chunk_schema

_SCHEMA_LOCK = 0x5EC0_0005  # advisory lock id; s-02..s-04 use 0x5EC0_0001..0x5EC0_0004


def schema_sql() -> str:
    return files("sec_agent.retrieval").joinpath("schema.sql").read_text("utf-8")


def apply_schema(conn: psycopg.Connection[Any]) -> None:
    """Apply the chunk schema, then `schema.sql` in one transaction under an advisory lock."""
    apply_chunk_schema(conn)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK,))
        conn.execute(schema_sql().encode())
