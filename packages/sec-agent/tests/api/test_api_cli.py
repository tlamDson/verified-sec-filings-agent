"""`sec-agent api init|serve`: the API's tables, and the checks before it starts."""

import psycopg
import pytest

from sec_agent.api.config import SECRET_ENV_VAR
from sec_agent.cli import main

TABLES = ("api_usage", "api_turns", "api_feedback")


def test_api_init_creates_the_tables_and_can_run_again(
    pg_uri: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["api", "--database-url", pg_uri, "init"]) == 0
    assert main(["api", "--database-url", pg_uri, "init"]) == 0
    assert "api schema ready" in capsys.readouterr().out
    with psycopg.connect(pg_uri) as conn:
        for table in TABLES:
            row = conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()
            assert row is not None
            assert row[0] == table, table


def test_the_tables_refuse_a_cohort_that_does_not_match_the_account(api_db: str) -> None:
    """Simulated rows can never be stored as real ones, whatever wrote them."""
    insert = (
        "INSERT INTO api_turns (user_id, cohort, thread_id, turn, asked_at, status, degraded)"
        " VALUES (%s, %s, 't-0000001', 1, now(), 'answered', false)"
    )
    with psycopg.connect(api_db, autocommit=True) as conn:
        for user_id, cohort in (("sim:sim-01@example.com", "real"), ("github:1", "simulated")):
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(insert, (user_id, cohort))
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(insert, ("github:1", "vip"))


def test_api_init_without_a_database_url_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["api", "init"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


@pytest.mark.parametrize("secret", [None, "too-short"])
def test_api_serve_refuses_to_start_without_a_usable_secret(
    pg_uri: str,
    secret: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(SECRET_ENV_VAR, raising=False)
    if secret is not None:
        monkeypatch.setenv(SECRET_ENV_VAR, secret)
    assert main(["api", "--database-url", pg_uri, "serve", "--facts-version", "x-test"]) == 2
    error = capsys.readouterr().err
    assert SECRET_ENV_VAR in error
    assert "too-short" not in error
