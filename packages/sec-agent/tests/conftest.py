"""Shared fixtures: a throwaway Postgres for queue tests, reachable only by a Unix socket.

The server binaries come from the `pgserver` wheel, but the server is started here, not by
pgserver: pgserver listens on TCP loopback on Windows. This fixture starts the server with
`listen_addresses` empty, so it opens no TCP port on any platform, and connects through a
socket file in a private temporary directory. No Docker, no network, nothing to set in CI.
"""

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


def _bin(name: str) -> str:
    import pgserver

    return str(Path(pgserver.__file__).parent / "pginstall" / "bin" / name)


def _run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture(scope="session")
def pg_uri(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("pg")
    data, socket_dir, log = root / "data", root / "s", root / "server.log"
    socket_dir.mkdir()
    _run(_bin("initdb"), "-D", str(data), "-U", "postgres", "--auth=trust", "--encoding=utf8")
    socket_path = socket_dir.as_posix()  # forward slashes: libpq reads backslash as escape
    server_options = f'-c listen_addresses= -k "{socket_path}"'  # socket only, no TCP
    try:
        _run(_bin("pg_ctl"), "-D", str(data), "-l", str(log), "-o", server_options, "-w", "start")
    except subprocess.CalledProcessError:
        pytest.fail(f"test Postgres did not start:\n{log.read_text('utf-8', 'replace')}")
    try:
        yield f"host='{socket_path}' user=postgres dbname=postgres"
    finally:
        _run(_bin("pg_ctl"), "-D", str(data), "-m", "immediate", "-w", "stop")


@pytest.fixture
def db_url(pg_uri: str) -> str:
    """The test database with the jobs schema applied and every table empty."""
    import psycopg

    from sec_agent.jobs.schema import apply_schema

    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE jobs RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS test_effects")
    return pg_uri


@pytest.fixture
def facts_db_url(pg_uri: str) -> str:
    """The test database with the jobs and facts schemas applied and every table empty."""
    import psycopg

    from sec_agent.jobs.schema import apply_schema as apply_jobs_schema
    from sec_agent.xbrl.schema import apply_schema as apply_facts_schema

    with psycopg.connect(pg_uri, autocommit=True) as conn:
        apply_jobs_schema(conn)
        apply_facts_schema(conn)
        conn.execute("TRUNCATE jobs, facts, xbrl_ingests RESTART IDENTITY")
    return pg_uri
