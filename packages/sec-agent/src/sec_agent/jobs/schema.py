"""Create the job queue tables. Safe to run from many workers at once."""

from importlib.resources import files
from typing import Any

import psycopg

_SCHEMA_LOCK = 0x5EC0_0001  # advisory lock id; serialises concurrent apply_schema calls


def schema_sql() -> str:
    return files("sec_agent.jobs").joinpath("schema.sql").read_text("utf-8")


def apply_schema(conn: psycopg.Connection[Any]) -> None:
    """Apply `schema.sql` in one transaction, under an advisory lock."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK,))
        conn.execute(schema_sql().encode())
