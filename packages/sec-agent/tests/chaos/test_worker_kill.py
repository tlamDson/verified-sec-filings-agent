"""Kill a worker process while it holds a job: the job is redone once, every job closes."""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from chaos_slow_worker import KIND

from sec_agent.chaos.worker_kill import (
    ChaosError,
    KillPlan,
    PostgresQueueProbe,
    kill_worker_mid_job,
    owner_pid,
)
from sec_agent.jobs.models import NewJob
from sec_agent.jobs.postgres import PostgresJobQueue

SCRIPT = Path(__file__).parent.parent / "chaos_slow_worker.py"


def test_owner_pid_reads_the_pid_from_a_worker_owner() -> None:
    assert owner_pid("host-1:4242:abcd1234") == 4242
    assert owner_pid("crashed-worker") is None
    assert owner_pid(None) is None


def test_killed_worker_job_is_taken_over_and_every_job_finishes(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS test_effects (key text PRIMARY KEY, runs int NOT NULL)"
        )
    keys = [f"slow-{i}" for i in range(4)]
    with PostgresJobQueue.connect(db_url) as queue:
        queue.enqueue([NewJob(kind=KIND, key=key) for key in keys])

    tests_dir = str(SCRIPT.parent)
    env = {**os.environ, "DATABASE_URL": db_url, "PYTHONPATH": tests_dir}

    def start() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, str(SCRIPT)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    with PostgresQueueProbe.connect(db_url, kinds=[KIND]) as probe:
        report = kill_worker_mid_job(
            probe, start, KillPlan(workers=2, timeout_seconds=60.0, poll_seconds=0.05)
        )

    assert report.workers == 2
    assert report.killed_job_key in keys
    assert report.killed_job_status == "done"
    assert report.killed_job_attempts == 2
    assert report.jobs_done == 4
    assert report.jobs_failed == 0
    assert report.seconds_to_recover > 0
    with psycopg.connect(db_url) as conn:
        effects = dict(conn.execute("SELECT key, runs FROM test_effects").fetchall())
    assert sorted(effects) == keys


class _IdleProbe:
    """A queue where no worker ever takes a job."""

    def running(self) -> list[tuple[int, str, str | None]]:
        return []

    def open_jobs(self) -> int:
        return 1

    def job(self, job_id: int) -> tuple[str, int]:
        raise AssertionError("no job was killed")

    def closed(self) -> tuple[int, int]:
        return (0, 0)


class _Sleeper:
    def __init__(self) -> None:
        self.pid = 999_999
        self.killed = False

    def poll(self) -> int | None:
        return -9 if self.killed else None

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return -9


def test_no_worker_taking_a_job_is_an_error_and_stops_the_workers() -> None:
    started: list[_Sleeper] = []

    def start() -> _Sleeper:
        started.append(_Sleeper())
        return started[-1]

    with pytest.raises(ChaosError, match="no worker took a job"):
        kill_worker_mid_job(
            _IdleProbe(), start, KillPlan(workers=2, timeout_seconds=0.2, poll_seconds=0.01)
        )
    assert len(started) == 2
    assert all(worker.killed for worker in started)


def test_plan_needs_a_survivor() -> None:
    with pytest.raises(ValueError, match="workers"):
        KillPlan(workers=1)
