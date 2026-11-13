"""Shared fixtures: a throwaway Postgres for queue tests.

`pgserver` ships Postgres binaries as a wheel and listens on a local socket (Linux, macOS)
or loopback (Windows). No Docker, no external network, nothing to configure in CI.
"""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from pgserver.postgres_server import get_server


@pytest.fixture(scope="session")
def pg_uri(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    data_dir: Path = tmp_path_factory.mktemp("pg")
    server = get_server(data_dir, cleanup_mode="stop")
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


@pytest.fixture
def db_url(pg_uri: str) -> str:
    """The test database with the jobs schema applied and every table empty."""
    from sec_agent.jobs.schema import apply_schema

    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE jobs RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS test_effects")
    return pg_uri
