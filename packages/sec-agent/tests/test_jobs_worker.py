"""Worker loop against an in-memory queue: dispatch, retry policy, heartbeats, fencing."""

import datetime as dt
import random
import threading
import uuid
from collections.abc import Collection, Iterable, Mapping

import pytest
from pydantic import ValidationError

from sec_agent.jobs.errors import PermanentJobError
from sec_agent.jobs.models import Job, JobStatus, NewJob
from sec_agent.jobs.worker import Handler, Outcome, Worker, WorkerConfig

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


class FakeQueue:
    """Hands out queued jobs in order and records what the worker reports back."""

    def __init__(self, jobs: Iterable[NewJob] = (), *, attempts: int = 1) -> None:
        self.pending = [self._job(i, new, attempts) for i, new in enumerate(jobs, start=1)]
        self.claimed_kinds: list[frozenset[str]] = []
        self.completed: list[int] = []
        self.failed: list[tuple[int, str, float | None]] = []
        self.heartbeats = 0
        self.heartbeat_errors = 0  # raise on this many heartbeats first
        self.lease_valid = True
        self.heartbeat_event = threading.Event()

    @staticmethod
    def _job(job_id: int, new: NewJob, attempts: int) -> Job:
        return Job(
            id=job_id,
            kind=new.kind,
            key=new.key,
            payload=new.payload,
            status="queued",
            attempts=attempts - 1,
            max_attempts=new.max_attempts,
            run_after=NOW,
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            last_error=None,
            created_at=NOW,
            updated_at=NOW,
            finished_at=None,
        )

    def enqueue(self, jobs: Iterable[NewJob]) -> int:
        raise NotImplementedError

    def claim(self, owner: str, kinds: Collection[str], lease_seconds: float) -> Job | None:
        self.claimed_kinds.append(frozenset(kinds))
        for index, job in enumerate(self.pending):
            if job.kind in kinds:
                del self.pending[index]
                return job.model_copy(
                    update={
                        "status": "running",
                        "attempts": job.attempts + 1,
                        "lease_owner": owner,
                        "lease_token": uuid.uuid4(),
                        "lease_expires_at": NOW + dt.timedelta(seconds=lease_seconds),
                    }
                )
        return None

    def heartbeat(self, job: Job, lease_seconds: float) -> bool:
        job.require_lease()
        self.heartbeats += 1
        if self.heartbeat_errors > 0:
            self.heartbeat_errors -= 1
            raise OSError("connection reset")
        self.heartbeat_event.set()
        return self.lease_valid

    def complete(self, job: Job) -> bool:
        self.completed.append(job.id)
        return self.lease_valid

    def fail(self, job: Job, error: str, retry_in: float | None) -> bool:
        self.failed.append((job.id, error, retry_in))
        return self.lease_valid

    def counts(self) -> dict[JobStatus, int]:
        raise NotImplementedError

    def get(self, job_id: int) -> Job | None:
        raise NotImplementedError


CONFIG = WorkerConfig(owner="test-worker", lease_seconds=1.0, heartbeat_seconds=0.02)


def _worker(queue: FakeQueue, handlers: Mapping[str, Handler], **config: float) -> Worker:
    return Worker(queue, handlers, CONFIG.model_copy(update=config), rng=random.Random(0))


def test_config_requires_heartbeat_shorter_than_lease() -> None:
    with pytest.raises(ValidationError, match="heartbeat"):
        WorkerConfig(owner="w", lease_seconds=10.0, heartbeat_seconds=10.0)


def test_worker_refuses_to_start_without_handlers() -> None:
    with pytest.raises(ValueError, match="no handlers"):
        Worker(FakeQueue(), {}, CONFIG)


def test_success_completes_the_job() -> None:
    seen: list[str] = []
    queue = FakeQueue([NewJob(kind="a.job", key="k1")])
    worker = _worker(queue, {"a.job": lambda job: seen.append(job.key)})
    assert worker.run_once() is Outcome.DONE
    assert seen == ["k1"]
    assert queue.completed == [1]
    assert queue.failed == []


def test_claims_only_kinds_it_has_handlers_for() -> None:
    queue = FakeQueue([NewJob(kind="b.job", key="k")])
    worker = _worker(queue, {"a.job": lambda job: None})
    assert worker.run_once() is None
    assert queue.claimed_kinds == [frozenset({"a.job"})]


def test_error_is_retried_with_backoff() -> None:
    def boom(job: Job) -> None:
        raise RuntimeError("HTTP 503 from SEC")

    queue = FakeQueue([NewJob(kind="a.job", key="k", max_attempts=3)])
    worker = _worker(queue, {"a.job": boom}, backoff_base_seconds=4.0, backoff_cap_seconds=60.0)
    assert worker.run_once() is Outcome.RETRY
    [(job_id, error, retry_in)] = queue.failed
    assert job_id == 1
    assert "RuntimeError" in error
    assert "HTTP 503 from SEC" in error
    assert retry_in is not None
    assert 0.0 <= retry_in <= 4.0
    assert queue.completed == []


def test_error_on_final_attempt_fails_for_good() -> None:
    def boom(job: Job) -> None:
        raise RuntimeError("still down")

    queue = FakeQueue([NewJob(kind="a.job", key="k", max_attempts=3)], attempts=3)
    worker = _worker(queue, {"a.job": boom})
    assert worker.run_once() is Outcome.FAILED
    assert queue.failed[0][2] is None


def test_permanent_error_is_not_retried() -> None:
    def reject(job: Job) -> None:
        raise PermanentJobError("CIK not found")

    queue = FakeQueue([NewJob(kind="a.job", key="k", max_attempts=5)])
    worker = _worker(queue, {"a.job": reject})
    assert worker.run_once() is Outcome.FAILED
    [(_, error, retry_in)] = queue.failed
    assert "CIK not found" in error
    assert retry_in is None


def test_heartbeats_while_handler_runs() -> None:
    queue = FakeQueue([NewJob(kind="a.job", key="k")])

    def slow(job: Job) -> None:
        for _ in range(3):
            assert queue.heartbeat_event.wait(2.0)
            queue.heartbeat_event.clear()

    worker = _worker(queue, {"a.job": slow})
    assert worker.run_once() is Outcome.DONE
    assert queue.heartbeats >= 3


def test_heartbeat_errors_do_not_kill_the_job() -> None:
    queue = FakeQueue([NewJob(kind="a.job", key="k")])
    queue.heartbeat_errors = 1
    worker = _worker(queue, {"a.job": lambda job: queue.heartbeat_event.wait(2.0)})
    assert worker.run_once() is Outcome.DONE
    assert queue.heartbeats >= 2


def test_lost_lease_is_reported_and_result_discarded() -> None:
    queue = FakeQueue([NewJob(kind="a.job", key="k")])
    queue.lease_valid = False
    worker = _worker(queue, {"a.job": lambda job: queue.heartbeat_event.wait(2.0)})
    assert worker.run_once() is Outcome.LEASE_LOST


def test_run_drain_processes_everything_then_stops() -> None:
    queue = FakeQueue([NewJob(kind="a.job", key=f"k{i}") for i in range(5)])
    worker = _worker(queue, {"a.job": lambda job: None})
    assert worker.run(drain=True) == 5
    assert queue.completed == [1, 2, 3, 4, 5]


def test_run_stops_when_event_is_set() -> None:
    queue = FakeQueue()
    worker = _worker(queue, {"a.job": lambda job: None}, poll_seconds=0.01)
    stop = threading.Event()
    timer = threading.Timer(0.1, stop.set)
    timer.start()
    assert worker.run(stop=stop) == 0
    timer.join()
    assert len(queue.claimed_kinds) >= 2
