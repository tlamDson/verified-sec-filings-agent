"""`sec-agent xbrl init|enqueue`."""

import pytest

from sec_agent.cli import main
from sec_agent.jobs.postgres import PostgresJobQueue


def test_xbrl_init_creates_the_facts_tables(
    pg_uri: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_uri)
    assert main(["xbrl", "init"]) == 0
    assert "facts schema ready" in capsys.readouterr().out


def test_xbrl_enqueue_adds_one_job_per_company_once(
    facts_db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", facts_db_url)
    assert main(["xbrl", "enqueue", "--index-version", "v1", "320193", "1045810"]) == 0
    assert "enqueued 2 of 2" in capsys.readouterr().out
    assert main(["xbrl", "enqueue", "--index-version", "v1", "320193"]) == 0
    assert "enqueued 0 of 1" in capsys.readouterr().out
    with PostgresJobQueue.connect(facts_db_url) as queue:
        assert queue.counts()["queued"] == 2
        job = queue.get(1)
    assert job is not None
    assert (job.kind, job.key) == ("xbrl.companyfacts", "v1:0000320193")


def test_xbrl_enqueue_rejects_a_bad_cik(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "host=/nonexistent dbname=none")
    assert main(["xbrl", "enqueue", "--index-version", "v1", "apple"]) == 2
    assert "CIK" in capsys.readouterr().err
