"""`sec-agent filings init|enqueue` and the `filing.sections` worker registration."""

import contextlib

import psycopg
import pytest

from sec_agent.cli import main
from sec_agent.filings.models import FILING_SECTIONS_KIND
from sec_agent.jobs.registry import HandlerContext, registered_handlers


def test_filings_init_creates_the_chunk_tables(
    pg_uri: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_uri)
    assert main(["filings", "init"]) == 0
    assert "ready" in capsys.readouterr().out
    with psycopg.connect(pg_uri) as conn:
        row = conn.execute("SELECT to_regclass('chunks') IS NOT NULL").fetchone()
    assert row == (True,)


def test_filings_enqueue_needs_a_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["filings", "enqueue", "320193"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_filings_enqueue_rejects_a_bad_window(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["enqueue", "1", "--report-from", "2025-01-01", "--report-to", "2024-01-01"]
    code = main(["filings", "--database-url", "x", *args])
    assert code == 2
    assert "report-from" in capsys.readouterr().err


def test_filing_sections_handler_is_registered() -> None:
    assert FILING_SECTIONS_KIND in registered_handlers()


def test_filing_sections_handler_needs_the_sec_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    factory = registered_handlers()[FILING_SECTIONS_KIND]
    with contextlib.ExitStack() as stack, pytest.raises(ValueError, match="SEC_USER_AGENT"):
        factory(HandlerContext(database_url="host=/nonexistent", resources=stack))


def test_worker_reports_a_missing_sec_user_agent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "host=/nonexistent dbname=none")
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert main(["worker", "--drain"]) == 2
    assert "SEC_USER_AGENT" in capsys.readouterr().err
