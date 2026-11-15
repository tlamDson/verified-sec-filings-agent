"""The test Postgres is reached only through a Unix socket: tests open no network port."""

import psycopg


def test_test_database_has_no_tcp_listener(pg_uri: str) -> None:
    with psycopg.connect(pg_uri) as conn:
        listen = conn.execute("SHOW listen_addresses").fetchone()
        server_addr = conn.execute("SELECT inet_server_addr()").fetchone()
    assert listen == ("",)
    assert server_addr == (None,)  # NULL means the session is on a Unix socket
