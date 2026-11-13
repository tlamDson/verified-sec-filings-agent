"""`sec-agent jobs init|stats` and `sec-agent worker`."""

import pytest

from sec_agent.cli import main
from sec_agent.jobs.models import NewJob
from sec_agent.jobs.postgres import PostgresJobQueue


def test_jobs_init_then_stats(
    pg_uri: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_uri)
    assert main(["jobs", "init"]) == 0
    with PostgresJobQueue.connect(pg_uri) as queue:
        queue.enqueue([NewJob(kind="cli.test", key="stats-check")])
    capsys.readouterr()
    assert main(["jobs", "stats"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == ["queued", "running", "done", "failed"]
    assert int(lines[0].split()[1]) >= 1


def test_database_url_flag_overrides_environment(
    pg_uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "host=/nonexistent dbname=none")
    assert main(["jobs", "--database-url", pg_uri, "init"]) == 0


def test_missing_database_url_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["jobs", "stats"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_worker_without_registered_handlers_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "host=/nonexistent dbname=none")
    monkeypatch.setattr("sec_agent.jobs.cli.registered_handlers", lambda _url: {})
    assert main(["worker", "--drain"]) == 2
    assert "no job handlers" in capsys.readouterr().err
