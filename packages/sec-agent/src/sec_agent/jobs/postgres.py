"""JobQueue on Postgres. One autocommit connection; one short transaction per call."""

import threading
from collections.abc import Collection, Iterable
from types import TracebackType
from typing import Self

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb

from sec_agent.jobs import sql
from sec_agent.jobs.models import JOB_STATUSES, Job, JobStatus, NewJob

_MAX_ERROR_CHARS = 4_000


class PostgresJobQueue:
    """Thread-safe: a worker's heartbeat thread shares the queue with its main thread."""

    def __init__(self, conn: psycopg.Connection[DictRow]) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    @classmethod
    def connect(cls, conninfo: str, *, statement_timeout_ms: int | None = None) -> Self:
        options = f"-c statement_timeout={statement_timeout_ms}" if statement_timeout_ms else ""
        conn = psycopg.Connection[DictRow].connect(
            conninfo, autocommit=True, row_factory=dict_row, options=options
        )
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def enqueue(self, jobs: Iterable[NewJob]) -> int:
        inserted = 0
        with self._lock, self._conn.transaction(), self._conn.cursor() as cur:
            for job in jobs:
                params = job.model_dump()
                params["payload"] = Jsonb(job.payload)
                cur.execute(sql.ENQUEUE, params)
                inserted += cur.rowcount
        return inserted

    def claim(self, owner: str, kinds: Collection[str], lease_seconds: float) -> Job | None:
        params = {"owner": owner, "kinds": list(kinds), "lease": lease_seconds}
        with self._lock, self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(sql.REAP_EXHAUSTED, params)
            row = cur.execute(sql.CLAIM, params).fetchone()
        return None if row is None else Job.model_validate(row)

    def heartbeat(self, job: Job, lease_seconds: float) -> bool:
        return self._fenced(sql.HEARTBEAT, job, lease=lease_seconds)

    def complete(self, job: Job) -> bool:
        return self._fenced(sql.COMPLETE, job)

    def fail(self, job: Job, error: str, retry_in: float | None) -> bool:
        error = error[:_MAX_ERROR_CHARS]
        if retry_in is None:
            return self._fenced(sql.FAIL, job, error=error)
        return self._fenced(sql.RETRY, job, error=error, retry_in=retry_in)

    def counts(self) -> dict[JobStatus, int]:
        result: dict[JobStatus, int] = dict.fromkeys(JOB_STATUSES, 0)
        with self._lock:
            for row in self._conn.execute(sql.COUNTS).fetchall():
                result[row["status"]] = row["n"]
        return result

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            row = self._conn.execute(sql.GET, {"id": job_id}).fetchone()
        return None if row is None else Job.model_validate(row)

    def _fenced(self, query: bytes, job: Job, **params: object) -> bool:
        params |= {"id": job.id, "token": job.require_lease()}
        with self._lock:
            return self._conn.execute(query, params).rowcount == 1
