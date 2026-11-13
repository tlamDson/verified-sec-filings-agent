"""`sec-agent agent init`: the tables the agent keeps in Postgres."""

import psycopg
import pytest

from sec_agent.cli import main

TABLES = ("llm_usage", "checkpoints", "checkpoint_blobs", "checkpoint_writes")


def test_agent_init_creates_the_usage_and_checkpoint_tables_and_can_run_again(
    pg_uri: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["agent", "--database-url", pg_uri, "init"]) == 0
    assert main(["agent", "--database-url", pg_uri, "init"]) == 0
    assert "agent schema ready" in capsys.readouterr().out
    with psycopg.connect(pg_uri) as conn:
        for table in TABLES:
            row = conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()
            assert row is not None
            assert row[0] == table, table


def test_agent_init_without_a_database_url_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["agent", "init"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err
