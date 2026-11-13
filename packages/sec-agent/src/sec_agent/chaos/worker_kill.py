"""Kill one worker process while it holds a job, then watch the queue recover.

Start N worker processes on a queued ingest, each with its own owner tag. As soon as a job
is running under one of them (the lease owner is `host:pid:tag`), kill that worker without
warning: the process this driver started and the pid the owner names, which differ when a
launcher (a Windows venv `python.exe`) runs the interpreter as a child. Its lease stops
being renewed, expires, and another worker takes the job over. Wait until no job is queued
or running, stop the survivors, and report what happened to the killed job. Whether facts
landed twice is `integrity.check_ingest`'s job.
"""

import os
import signal
import time
from collections.abc import Callable, Collection, Generator, Sequence
from contextlib import contextmanager, suppress
from typing import Any, Protocol, Self

import psycopg
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChaosError(Exception):
    """The chaos run could not do what it set out to do; nothing is measured."""


class WorkerProcess(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class QueueProbe(Protocol):
    def running(self) -> list[tuple[int, str, str | None]]:
        """(job id, key, lease owner) of every running job."""
        ...

    def open_jobs(self) -> int:
        """Jobs queued or running."""
        ...

    def job(self, job_id: int) -> tuple[str, int]:
        """(status, attempts) of one job."""
        ...

    def closed(self) -> tuple[int, int]:
        """(done, failed) job counts."""
        ...


class KillPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workers: int = Field(default=3, ge=2, le=16)
    """At least two: one to kill and one to take its job over."""
    timeout_seconds: float = Field(default=600.0, gt=0)
    poll_seconds: float = Field(default=0.1, gt=0)


class KillReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workers: int
    killed_pid: int
    killed_job_id: int
    killed_job_key: str
    killed_job_status: str
    killed_job_attempts: int
    jobs_done: int
    jobs_failed: int
    seconds_to_recover: float
    """From the kill until no job was queued or running."""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.seconds_to_recover < 0:
            raise ValueError("seconds_to_recover cannot be negative")
        return self


def owner_pid(owner: str | None) -> int | None:
    """The pid in a worker's lease owner `host:pid:tag`, or None for any other owner."""
    parts = _owner_parts(owner)
    return int(parts[1]) if parts else None


def owner_tag(owner: str | None) -> str | None:
    """The tag in a worker's lease owner `host:pid:tag`, or None for any other owner."""
    parts = _owner_parts(owner)
    return parts[2] if parts else None


def _owner_parts(owner: str | None) -> list[str] | None:
    if owner is None:
        return None
    parts = owner.rsplit(":", 2)
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2]:
        return None
    return parts


def kill_pid(pid: int) -> None:
    """Kill a process at once (SIGKILL; TerminateProcess on Windows). Gone already is fine."""
    with suppress(OSError):  # ProcessLookupError and PermissionError are OSErrors
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))


def kill_worker_mid_job[P: WorkerProcess](
    probe: QueueProbe,
    start_worker: Callable[[str], P],
    plan: KillPlan,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    kill: Callable[[int], None] = kill_pid,
) -> KillReport:
    """`start_worker(tag)` starts one worker whose lease owner ends in `:tag`."""
    tagged = {f"chaos-{index}": start_worker(f"chaos-{index}") for index in range(plan.workers)}
    workers = list(tagged.values())
    try:
        deadline = clock() + plan.timeout_seconds
        victim, pid, job_id, key = _await_victim(probe, tagged, plan, deadline, clock, sleep)
        victim.kill()
        kill(pid)
        victim.wait(timeout=plan.timeout_seconds)
        killed_at = clock()
        survivors = [worker for worker in workers if worker is not victim]
        _await_drain(probe, survivors, plan, deadline, clock, sleep)
        recovered = clock() - killed_at
        status, attempts = probe.job(job_id)
        done, failed = probe.closed()
        return KillReport(
            workers=plan.workers,
            killed_pid=pid,
            killed_job_id=job_id,
            killed_job_key=key,
            killed_job_status=status,
            killed_job_attempts=attempts,
            jobs_done=done,
            jobs_failed=failed,
            seconds_to_recover=recovered,
        )
    finally:
        _stop(workers)


def _await_victim[P: WorkerProcess](
    probe: QueueProbe,
    tagged: dict[str, P],
    plan: KillPlan,
    deadline: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[P, int, int, str]:
    """(process, worker pid, job id, job key) of the first of our workers seen on a job."""
    while clock() < deadline:
        for job_id, key, owner in probe.running():
            worker = tagged.get(owner_tag(owner) or "")
            pid = owner_pid(owner)
            if worker is not None and pid is not None and worker.poll() is None:
                return worker, pid, job_id, key
        if all(worker.poll() is not None for worker in tagged.values()):
            raise ChaosError("every worker exited before taking a job")
        sleep(plan.poll_seconds)
    raise ChaosError("no worker took a job before the timeout")


def _await_drain(
    probe: QueueProbe,
    survivors: Sequence[WorkerProcess],
    plan: KillPlan,
    deadline: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> None:
    while probe.open_jobs() > 0:
        if all(worker.poll() is not None for worker in survivors):
            raise ChaosError("every surviving worker exited with jobs still open")
        if clock() >= deadline:
            raise ChaosError("jobs were still open at the timeout")
        sleep(plan.poll_seconds)


def _stop(workers: Sequence[WorkerProcess]) -> None:
    for worker in workers:
        if worker.poll() is None:
            worker.kill()
    for worker in workers:
        worker.wait(timeout=30)


class PostgresQueueProbe:
    """The probe over the `jobs` table, limited to some job kinds (and a key prefix)."""

    def __init__(
        self, conn: psycopg.Connection[Any], kinds: Collection[str], key_prefix: str = ""
    ) -> None:
        self._conn = conn
        self._params: dict[str, Any] = {"kinds": list(kinds), "prefix": key_prefix}

    @classmethod
    @contextmanager
    def connect(cls, url: str, *, kinds: Collection[str], key_prefix: str = "") -> Generator[Self]:
        with psycopg.connect(url, autocommit=True) as conn:
            yield cls(conn, kinds, key_prefix)

    def running(self) -> list[tuple[int, str, str | None]]:
        rows = self._conn.execute(
            b"SELECT id, key, lease_owner FROM jobs WHERE status = 'running' "
            b"AND kind = ANY(%(kinds)s) AND starts_with(key, %(prefix)s) ORDER BY id",
            self._params,
        ).fetchall()
        return [(int(row[0]), str(row[1]), row[2]) for row in rows]

    def open_jobs(self) -> int:
        return self._count(b"status IN ('queued', 'running')")

    def job(self, job_id: int) -> tuple[str, int]:
        row = self._conn.execute(
            b"SELECT status, attempts FROM jobs WHERE id = %s", (job_id,)
        ).fetchone()
        if row is None:
            raise ChaosError(f"job {job_id} disappeared")
        return str(row[0]), int(row[1])

    def closed(self) -> tuple[int, int]:
        return self._count(b"status = 'done'"), self._count(b"status = 'failed'")

    def _count(self, condition: bytes) -> int:
        row = self._conn.execute(
            b"SELECT count(*) FROM jobs WHERE "
            + condition
            + b" AND kind = ANY(%(kinds)s) AND starts_with(key, %(prefix)s)",
            self._params,
        ).fetchone()
        return int(row[0]) if row else 0
