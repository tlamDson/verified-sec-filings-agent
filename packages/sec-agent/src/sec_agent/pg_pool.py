"""Postgres connections that survive the server closing them.

A hosted database closes idle connections and restarts; a connection kept for the life of
the process would then fail every later call until the process restarts. A pool checks a
connection each time it lends it and replaces one the server has closed.

`Connections` is a pool or one plain connection (tests, one-shot commands), and `lease`
lends a connection from either.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

Pool = ConnectionPool[psycopg.Connection[Any]]
Connections = psycopg.Connection[Any] | Pool


def open_pool(conninfo: str, **kwargs: Any) -> Pool:
    """An open pool of one autocommit connection, checked before each lease.

    One connection, as before pooling, so a replica holds no more server connections than
    it did. The first connection is made here, so a bad URL fails at start as it did.
    """
    options: dict[str, Any] = {"autocommit": True, **kwargs}
    psycopg.connect(conninfo, **options).close()  # fail fast, with psycopg's own error
    pool: Pool = ConnectionPool(
        conninfo,
        min_size=1,
        max_size=1,
        kwargs=options,
        check=ConnectionPool.check_connection,
        open=False,
    )
    pool.open(wait=True)
    return pool


@contextmanager
def pooled(conninfo: str, **kwargs: Any) -> Generator[Pool]:
    """`open_pool`, closed when the block ends."""
    with open_pool(conninfo, **kwargs) as pool:
        yield pool


@contextmanager
def lease(source: Connections) -> Generator[psycopg.Connection[Any]]:
    """A live connection from a pool, or the plain connection itself."""
    if isinstance(source, ConnectionPool):
        with source.connection() as conn:
            yield conn
    else:
        yield source
