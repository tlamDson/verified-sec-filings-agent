"""After an ingest with a crashed worker: no fact twice, every company whole, every job closed."""

import time
from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from xbrl_docs import APPLE, NVIDIA

from sec_agent.chaos.integrity import check_ingest
from sec_agent.edgar.urls import companyfacts_url
from sec_agent.jobs.postgres import PostgresJobQueue
from sec_agent.jobs.worker import Worker, WorkerConfig
from sec_agent.xbrl.ingest import KIND, companyfacts_job, make_handler
from sec_agent.xbrl.store import PostgresFactStore

BODIES = {companyfacts_url(320193): APPLE, companyfacts_url(1045810): NVIDIA}


def _fetch(url: str, refresh: bool) -> bytes:
    return BODIES[url].read_bytes()


@contextmanager
def _ingested(facts_db_url: str, *, crash_first: bool) -> Generator[None]:
    handler = make_handler(_fetch, lambda: PostgresFactStore.connect(facts_db_url))
    config = WorkerConfig(owner="survivor", lease_seconds=5.0, heartbeat_seconds=1.0)
    with PostgresJobQueue.connect(facts_db_url) as queue:
        queue.enqueue([companyfacts_job(320193, "v1"), companyfacts_job(1045810, "v1")])
        if crash_first:
            assert queue.claim("crashed", [KIND], 0.2) is not None  # dies without reporting
            time.sleep(0.4)
        Worker(queue, {KIND: handler}, config).run(drain=True)
    yield


def test_clean_ingest_has_no_duplicates_and_closes_every_job(facts_db_url: str) -> None:
    with _ingested(facts_db_url, crash_first=False), psycopg.connect(facts_db_url) as conn:
        report = check_ingest(conn, "v1")
    assert report.jobs_total == 2
    assert report.jobs_done == 2
    assert report.jobs_open == 0
    assert report.jobs_redone == 0
    assert report.duplicate_fact_keys == 0
    assert report.companies_ingested == 2
    assert report.companies_short == 0
    assert report.clean


def test_job_redone_after_crash_is_counted_and_leaves_no_duplicate(facts_db_url: str) -> None:
    with _ingested(facts_db_url, crash_first=True), psycopg.connect(facts_db_url) as conn:
        report = check_ingest(conn, "v1")
    assert report.jobs_done == 2
    assert report.jobs_redone == 1
    assert report.duplicate_fact_keys == 0
    assert report.clean


def test_other_index_versions_are_not_counted(facts_db_url: str) -> None:
    with _ingested(facts_db_url, crash_first=False), psycopg.connect(facts_db_url) as conn:
        report = check_ingest(conn, "v2")
    assert (report.jobs_total, report.companies_ingested) == (0, 0)
    assert not report.clean  # nothing ingested is not a clean ingest


def test_a_duplicate_fact_row_is_found(facts_db_url: str) -> None:
    """The unique key forbids it; drop the key inside a rolled-back transaction to prove
    the check would see one if the key were ever lost."""
    with _ingested(facts_db_url, crash_first=False), psycopg.connect(facts_db_url) as conn:
        conn.execute("ALTER TABLE facts DROP CONSTRAINT facts_version_unique")
        conn.execute("INSERT INTO facts SELECT * FROM facts WHERE index_version = 'v1' LIMIT 1")
        report = check_ingest(conn, "v1")
        conn.rollback()
    assert report.duplicate_fact_keys == 1
    assert not report.clean


def test_a_company_missing_facts_is_found(facts_db_url: str) -> None:
    with _ingested(facts_db_url, crash_first=False), psycopg.connect(facts_db_url) as conn:
        conn.execute(
            "DELETE FROM facts WHERE ctid IN (SELECT ctid FROM facts WHERE cik = 320193 LIMIT 3)"
        )
        report = check_ingest(conn, "v1")
        conn.rollback()
    assert report.companies_short == 1
    assert not report.clean
