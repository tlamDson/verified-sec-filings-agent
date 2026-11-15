"""PostgresJobQueue against a real Postgres: dedup, SKIP LOCKED, leases, retries."""

import threading
import time
from collections.abc import Iterator

import psycopg
import pytest

from sec_agent.jobs.models import Job, NewJob
from sec_agent.jobs.postgres import PostgresJobQueue
from sec_agent.jobs.schema import apply_schema

KINDS = ("xbrl.companyfacts", "filing.sections")
LEASE = 30.0
SHORT_LEASE = 0.3


@pytest.fixture
def queue(db_url: str) -> Iterator[PostgresJobQueue]:
    with PostgresJobQueue.connect(db_url) as q:
        yield q


def _claim(queue: PostgresJobQueue, owner: str = "w1", lease: float = LEASE) -> Job:
    job = queue.claim(owner, KINDS, lease)
    assert job is not None
    return job


def test_apply_schema_is_idempotent(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        apply_schema(conn)
        apply_schema(conn)


def test_enqueue_dedups_on_kind_and_key(queue: PostgresJobQueue) -> None:
    first = [NewJob(kind="xbrl.companyfacts", key="0000320193")]
    assert queue.enqueue(first) == 1
    again = [
        NewJob(kind="xbrl.companyfacts", key="0000320193"),
        NewJob(kind="filing.sections", key="0000320193"),
    ]
    assert queue.enqueue(again) == 1
    assert queue.counts()["queued"] == 2


def test_claim_leases_the_oldest_ready_job(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key=k, payload={"cik": k}) for k in "ab"])
    job = _claim(queue, owner="worker-1")
    assert (job.key, job.payload) == ("a", {"cik": "a"})
    assert job.status == "running"
    assert job.attempts == 1
    assert job.lease_owner == "worker-1"
    assert job.lease_token is not None
    assert job.lease_expires_at is not None
    assert job.lease_expires_at > job.updated_at


def test_claim_only_takes_requested_kinds(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="other.kind", key="x")])
    assert queue.claim("w1", KINDS, LEASE) is None
    assert queue.claim("w1", ["other.kind"], LEASE) is not None


def test_claim_returns_none_when_empty(queue: PostgresJobQueue) -> None:
    assert queue.claim("w1", KINDS, LEASE) is None


def test_claim_skips_rows_locked_by_another_transaction(db_url: str) -> None:
    """FOR UPDATE SKIP LOCKED: a locked row is passed over at once, never waited on."""
    # The statement timeout turns a claim that would block into an error instead of a hang.
    with (
        PostgresJobQueue.connect(db_url, statement_timeout_ms=2_000) as queue,
        psycopg.connect(db_url) as other,
    ):
        queue.enqueue([NewJob(kind="xbrl.companyfacts", key=k) for k in ("first", "second")])
        other.execute("SELECT id FROM jobs WHERE key = 'first' FOR UPDATE")  # open transaction
        job = _claim(queue)
        assert job.key == "second"
        other.rollback()


def test_concurrent_claimers_never_share_a_job(db_url: str) -> None:
    total = 60
    with PostgresJobQueue.connect(db_url) as setup:
        setup.enqueue([NewJob(kind="xbrl.companyfacts", key=f"k{i:03}") for i in range(total)])

    claimed: list[int] = []
    lock = threading.Lock()

    def drain(owner: str) -> None:
        with PostgresJobQueue.connect(db_url) as q:
            while (job := q.claim(owner, KINDS, LEASE)) is not None:
                with lock:
                    claimed.append(job.id)

    threads = [threading.Thread(target=drain, args=(f"w{i}",)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(claimed) == total
    assert len(set(claimed)) == total


def test_heartbeat_extends_lease(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key="a")])
    job = _claim(queue, lease=5.0)
    assert queue.heartbeat(job, 120.0)
    renewed = queue.get(job.id)
    assert renewed is not None
    assert renewed.lease_expires_at is not None
    assert job.lease_expires_at is not None
    assert renewed.lease_expires_at > job.lease_expires_at


def test_expired_lease_is_reclaimed_and_old_holder_is_fenced(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key="a")])
    stale = _claim(queue, owner="dead-worker", lease=SHORT_LEASE)
    time.sleep(SHORT_LEASE * 2)
    fresh = _claim(queue, owner="live-worker")
    assert fresh.id == stale.id
    assert fresh.attempts == 2
    assert fresh.lease_owner == "live-worker"
    assert fresh.lease_token != stale.lease_token
    assert not queue.heartbeat(stale, LEASE)
    assert not queue.complete(stale)
    assert not queue.fail(stale, "late", retry_in=1.0)
    assert queue.complete(fresh)


def test_live_lease_is_not_reclaimed(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key="a")])
    _claim(queue)
    assert queue.claim("w2", KINDS, LEASE) is None


def test_expired_lease_on_final_attempt_fails_the_job(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key="a", max_attempts=1)])
    job = _claim(queue, lease=SHORT_LEASE)
    time.sleep(SHORT_LEASE * 2)
    assert queue.claim("w2", KINDS, LEASE) is None
    failed = queue.get(job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error is not None
    assert "lease expired" in failed.last_error
    assert failed.lease_token is None


def test_complete_marks_done_and_job_is_not_claimed_again(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key="a")])
    job = _claim(queue)
    assert queue.complete(job)
    done = queue.get(job.id)
    assert done is not None
    assert done.status == "done"
    assert done.finished_at is not None
    assert done.lease_token is None
    assert queue.claim("w1", KINDS, LEASE) is None


def test_fail_with_retry_requeues_after_delay(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key="a")])
    job = _claim(queue)
    assert queue.fail(job, "HTTP 503", retry_in=SHORT_LEASE)
    retried = queue.get(job.id)
    assert retried is not None
    assert (retried.status, retried.last_error, retried.lease_token) == ("queued", "HTTP 503", None)
    assert queue.claim("w1", KINDS, LEASE) is None  # not ready yet
    time.sleep(SHORT_LEASE * 2)
    again = _claim(queue)
    assert again.attempts == 2


def test_fail_without_retry_is_final(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key="a")])
    job = _claim(queue)
    assert queue.fail(job, "bad payload", retry_in=None)
    failed = queue.get(job.id)
    assert failed is not None
    assert (failed.status, failed.last_error) == ("failed", "bad payload")
    assert failed.finished_at is not None
    assert queue.claim("w1", KINDS, LEASE) is None


def test_counts_cover_every_status(queue: PostgresJobQueue) -> None:
    queue.enqueue([NewJob(kind="xbrl.companyfacts", key=k) for k in "abcd"])
    queue.complete(_claim(queue))
    queue.fail(_claim(queue), "x", retry_in=None)
    _claim(queue)
    assert queue.counts() == {"queued": 1, "running": 1, "done": 1, "failed": 1}


def test_get_unknown_job_is_none(queue: PostgresJobQueue) -> None:
    assert queue.get(999) is None
