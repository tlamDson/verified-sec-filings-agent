"""Drop a process's Postgres connections from the server side, as a hosted database does
on an idle timeout or a restart: `pg_terminate_backend` on the backends a test opened.
"""

import psycopg

_CLIENTS = """
SELECT pid FROM pg_stat_activity
WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()
"""


def client_backends(url: str) -> set[int]:
    with psycopg.connect(url, autocommit=True) as conn:
        return {int(row[0]) for row in conn.execute(_CLIENTS)}


def terminate(url: str, pids: set[int]) -> None:
    """Kill these backends and wait until the server has removed them."""
    assert pids, "no backend to terminate"
    with psycopg.connect(url, autocommit=True) as conn:
        for pid in pids:
            conn.execute("SELECT pg_terminate_backend(%s, 5000)", (pid,))
