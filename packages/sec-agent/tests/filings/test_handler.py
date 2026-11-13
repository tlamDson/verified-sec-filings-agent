"""The `filing.sections` job: fetch one filing through EDGAR, index it, store it."""

import datetime as dt
from collections.abc import Callable

import psycopg
import pytest

from sec_agent.edgar.errors import EdgarNotFoundError, EdgarUnavailableError
from sec_agent.filings.handler import make_filing_handler
from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import FILING_SECTIONS_KIND, FilingJob, FilingRef, IndexedFiling
from sec_agent.filings.store import PostgresChunkStore
from sec_agent.jobs.errors import PermanentJobError
from sec_agent.jobs.models import Job
from sec_agent.jobs.postgres import PostgresJobQueue
from sec_agent.jobs.worker import Worker, WorkerConfig

CONFIG = ChunkConfig()
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


class FakeStore:
    def __init__(self) -> None:
        self.stored: list[IndexedFiling] = []

    def replace(self, indexed: IndexedFiling) -> None:
        self.stored.append(indexed)


def _job(payload: dict[str, object]) -> Job:
    return Job.model_validate(
        {
            "id": 1,
            "kind": FILING_SECTIONS_KIND,
            "key": "k",
            "payload": payload,
            "status": "running",
            "attempts": 1,
            "max_attempts": 5,
            "run_after": NOW,
            "lease_owner": "w",
            "lease_token": None,
            "lease_expires_at": None,
            "last_error": None,
            "created_at": NOW,
            "updated_at": NOW,
            "finished_at": None,
        }
    )


def _payload(filing: FilingRef, version: str | None = None) -> dict[str, object]:
    job = FilingJob(index_version=version or index_version(CONFIG), filing=filing)
    return job.to_new_job().payload


def test_job_key_is_version_and_accession(filing_10k: FilingRef) -> None:
    new = FilingJob(index_version=index_version(CONFIG), filing=filing_10k).to_new_job()
    assert new.kind == "filing.sections"
    assert new.key == f"{index_version(CONFIG)}/{filing_10k.accession}"


def test_handler_fetches_the_primary_document_and_stores_its_index(
    read_fixture: Callable[[str], bytes], filing_10k: FilingRef
) -> None:
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return read_fixture("sim-10k.htm")

    store = FakeStore()
    make_filing_handler(fetch, store, CONFIG)(_job(_payload(filing_10k)))
    assert fetched == [filing_10k.document_url]
    (indexed,) = store.stored
    assert indexed.filing == filing_10k
    assert indexed.index_version == index_version(CONFIG)
    assert len(indexed.sections) == 4


def test_job_for_another_index_version_fails_permanently(filing_10k: FilingRef) -> None:
    handler = make_filing_handler(lambda url: b"", FakeStore(), CONFIG)
    with pytest.raises(PermanentJobError, match="chunks-p0-t1-deadbeef"):
        handler(_job(_payload(filing_10k, "chunks-p0-t1-deadbeef")))


def test_malformed_payload_fails_permanently() -> None:
    handler = make_filing_handler(lambda url: b"", FakeStore(), CONFIG)
    with pytest.raises(PermanentJobError, match="payload"):
        handler(_job({"index_version": index_version(CONFIG)}))


def test_missing_document_fails_permanently(filing_10k: FilingRef) -> None:
    def fetch(url: str) -> bytes:
        raise EdgarNotFoundError(url)

    handler = make_filing_handler(fetch, FakeStore(), CONFIG)
    with pytest.raises(PermanentJobError, match="404"):
        handler(_job(_payload(filing_10k)))


def test_sec_unavailable_is_left_to_the_retry_policy(filing_10k: FilingRef) -> None:
    def fetch(url: str) -> bytes:
        raise EdgarUnavailableError(url, 5, 503)

    handler = make_filing_handler(fetch, FakeStore(), CONFIG)
    with pytest.raises(EdgarUnavailableError):
        handler(_job(_payload(filing_10k)))


def test_worker_drains_filing_jobs_into_postgres_exactly_once(
    chunk_db: str,
    read_fixture: Callable[[str], bytes],
    filing_10k: FilingRef,
    filing_10q: FilingRef,
) -> None:
    documents = {
        filing_10k.document_url: read_fixture("sim-10k.htm"),
        filing_10q.document_url: read_fixture("sim-10q.htm"),
    }
    jobs = [
        FilingJob(index_version=index_version(CONFIG), filing=f).to_new_job()
        for f in (filing_10k, filing_10q)
    ]
    with (
        PostgresJobQueue.connect(chunk_db) as queue,
        PostgresChunkStore.connect(chunk_db) as store,
    ):
        assert queue.enqueue(jobs) == 2
        assert queue.enqueue(jobs) == 0
        handler = make_filing_handler(documents.__getitem__, store, CONFIG)
        worker = Worker(queue, {FILING_SECTIONS_KIND: handler}, WorkerConfig(owner="t"))
        assert worker.run(drain=True) == 2
        assert queue.counts()["done"] == 2
        handler(_job(_payload(filing_10k)))  # a duplicate delivery changes nothing
    with psycopg.connect(chunk_db) as conn:
        rows = conn.execute(
            "SELECT form, array_agg(DISTINCT section ORDER BY section) FROM chunks"
            " GROUP BY form ORDER BY form"
        ).fetchall()
        filings = conn.execute("SELECT count(*) FROM indexed_filings").fetchone()
    assert rows == [
        ("10-K", ["business", "market_risk", "mdna", "risk_factors"]),
        ("10-Q", ["mdna", "risk_factors"]),
    ]
    assert filings == (2,)
