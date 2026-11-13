"""The `xbrl.companyfacts` job: fetch through the EDGAR client, normalise, upsert."""

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager

import pytest
from pydantic import JsonValue
from xbrl_docs import APPLE

from sec_agent.edgar.errors import EdgarNotFoundError, EdgarUnavailableError
from sec_agent.edgar.urls import companyfacts_url
from sec_agent.jobs.errors import PermanentJobError
from sec_agent.jobs.models import Job
from sec_agent.jobs.registry import registered_handlers
from sec_agent.xbrl.ingest import KIND, companyfacts_job, make_handler
from sec_agent.xbrl.store import PostgresFactStore

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


class FakeFetch:
    """Serves the recorded Apple document, or raises; records every call."""

    def __init__(self, body: bytes = b"", error: Exception | None = None) -> None:
        self.body = body or APPLE.read_bytes()
        self.error = error
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, url: str, refresh: bool) -> bytes:
        self.calls.append((url, refresh))
        if self.error is not None:
            raise self.error
        return self.body


def _job(payload: dict[str, JsonValue]) -> Job:
    return Job(
        id=1,
        kind=KIND,
        key="k",
        payload=payload,
        status="running",
        attempts=1,
        max_attempts=5,
        run_after=NOW,
        lease_owner="w",
        lease_token=None,
        lease_expires_at=None,
        last_error=None,
        created_at=NOW,
        updated_at=NOW,
        finished_at=None,
    )


@pytest.fixture
def open_store(facts_db_url: str) -> Callable[[], AbstractContextManager[PostgresFactStore]]:
    return lambda: PostgresFactStore.connect(facts_db_url)


@pytest.fixture
def check_store(facts_db_url: str) -> Iterator[PostgresFactStore]:
    with PostgresFactStore.connect(facts_db_url) as s:
        yield s


def test_companyfacts_job_is_keyed_by_index_version_and_cik() -> None:
    job = companyfacts_job(320193, "v1")
    assert (job.kind, job.key) == ("xbrl.companyfacts", "v1:0000320193")
    assert job.payload == {"cik": "0000320193", "index_version": "v1", "refresh": False}
    assert companyfacts_job("0000320193", "v1", refresh=True).payload["refresh"] is True


@pytest.mark.parametrize(("cik", "version"), [(0, "v1"), ("abc", "v1"), (1, ""), (1, "V 1")])
def test_companyfacts_job_rejects_bad_input(cik: int | str, version: str) -> None:
    with pytest.raises(ValueError, match=r".+"):
        companyfacts_job(cik, version)


def test_handler_fetches_normalises_and_writes(
    open_store: Callable[[], AbstractContextManager[PostgresFactStore]],
    check_store: PostgresFactStore,
) -> None:
    fetch = FakeFetch()
    handler = make_handler(fetch, open_store)
    handler(_job(companyfacts_job(320193, "v1").payload))
    assert fetch.calls == [(companyfacts_url(320193), False)]
    written = check_store.count(index_version="v1", cik=320193)
    assert written > 1000
    record = check_store.ingest_record(index_version="v1", cik=320193)
    assert record is not None
    assert record.facts_written == written


def test_running_the_job_twice_has_one_effect(
    open_store: Callable[[], AbstractContextManager[PostgresFactStore]],
    check_store: PostgresFactStore,
) -> None:
    handler = make_handler(FakeFetch(), open_store)
    job = _job(companyfacts_job(320193, "v1").payload)
    handler(job)
    once = check_store.count(index_version="v1", cik=320193)
    handler(job)
    assert check_store.count(index_version="v1", cik=320193) == once


def test_refresh_flag_reaches_the_client(
    open_store: Callable[[], AbstractContextManager[PostgresFactStore]],
) -> None:
    fetch = FakeFetch()
    make_handler(fetch, open_store)(_job(companyfacts_job(320193, "v1", refresh=True).payload))
    assert fetch.calls[0][1] is True


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"cik": "0000320193"},
        {"cik": "x", "index_version": "v1"},
        {"cik": "0000320193", "index_version": "v1", "extra": 1},
    ],
)
def test_bad_payload_is_a_permanent_failure(payload: dict[str, JsonValue]) -> None:
    fetch = FakeFetch()
    handler = make_handler(fetch, lambda: pytest.fail("no store needed"))
    with pytest.raises(PermanentJobError):
        handler(_job(payload))
    assert fetch.calls == []


def test_company_without_xbrl_facts_is_a_permanent_failure() -> None:
    url = companyfacts_url(320193)
    handler = make_handler(FakeFetch(error=EdgarNotFoundError(url)), lambda: pytest.fail("x"))
    with pytest.raises(PermanentJobError, match="404"):
        handler(_job(companyfacts_job(320193, "v1").payload))


def test_sec_unavailable_is_retried_by_the_queue() -> None:
    error = EdgarUnavailableError(companyfacts_url(320193), 5, 503)
    handler = make_handler(FakeFetch(error=error), lambda: pytest.fail("x"))
    with pytest.raises(EdgarUnavailableError):
        handler(_job(companyfacts_job(320193, "v1").payload))


def test_document_for_another_company_is_a_permanent_failure() -> None:
    handler = make_handler(FakeFetch(), lambda: pytest.fail("x"))
    with pytest.raises(PermanentJobError, match="CIK"):
        handler(_job(companyfacts_job(1045810, "v1").payload))


def test_malformed_document_is_a_permanent_failure() -> None:
    handler = make_handler(FakeFetch(body=b"<html>"), lambda: pytest.fail("x"))
    with pytest.raises(PermanentJobError):
        handler(_job(companyfacts_job(320193, "v1").payload))


def test_worker_registry_offers_the_companyfacts_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner tests@example.org")
    handlers = registered_handlers("host=/nonexistent dbname=none")
    assert set(handlers) == {"xbrl.companyfacts"}
