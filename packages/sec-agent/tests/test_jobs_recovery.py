"""Workers on a real Postgres: a crashed worker's job is redone once, with one effect."""

import threading
import time

import psycopg

from sec_agent.jobs.models import Job, NewJob
from sec_agent.jobs.postgres import PostgresJobQueue
from sec_agent.jobs.worker import Handler, Outcome, Worker, WorkerConfig

KIND = "xbrl.companyfacts"


def _effect_handler(db_url: str) -> Handler:
    """A handler whose write is keyed, like the real ingest upserts by accession number."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS test_effects (key text PRIMARY KEY, runs int NOT NULL)"
        )

    def handle(job: Job) -> None:
        with psycopg.connect(db_url, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO test_effects (key, runs) VALUES (%s, 1) "
                "ON CONFLICT (key) DO UPDATE SET runs = test_effects.runs + 1",
                (job.key,),
            )

    return handle


def _effects(db_url: str) -> list[tuple[str, int]]:
    with psycopg.connect(db_url) as conn:
        return conn.execute("SELECT key, runs FROM test_effects ORDER BY key").fetchall()


def test_job_of_crashed_worker_is_redone_after_lease_expiry(db_url: str) -> None:
    handle = _effect_handler(db_url)
    config = WorkerConfig(owner="survivor", lease_seconds=5.0, heartbeat_seconds=1.0)
    with PostgresJobQueue.connect(db_url) as queue:
        queue.enqueue([NewJob(kind=KIND, key="0000320193")])
        crashed = queue.claim("crashed-worker", [KIND], 0.3)  # claims, then never reports
        assert crashed is not None
        time.sleep(0.6)
        assert Worker(queue, {KIND: handle}, config).run_once() is Outcome.DONE
        assert queue.counts()["done"] == 1
        assert not queue.complete(crashed)  # a late report from the crashed worker is refused
    assert _effects(db_url) == [("0000320193", 1)]


def test_parallel_workers_process_every_job_exactly_once(db_url: str) -> None:
    handle = _effect_handler(db_url)
    keys = [f"cik-{i:03}" for i in range(40)]
    with PostgresJobQueue.connect(db_url) as queue:
        queue.enqueue([NewJob(kind=KIND, key=k) for k in keys])

    processed: list[int] = []

    def run(owner: str) -> None:
        config = WorkerConfig(owner=owner, lease_seconds=30.0, heartbeat_seconds=5.0)
        with PostgresJobQueue.connect(db_url) as q:
            processed.append(Worker(q, {KIND: handle}, config).run(drain=True))

    threads = [threading.Thread(target=run, args=(f"w{i}",)) for i in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(processed) == len(keys)
    assert _effects(db_url) == [(k, 1) for k in keys]
