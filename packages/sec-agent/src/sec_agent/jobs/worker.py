"""Worker loop: claim a job, run its handler under a heartbeat, report the outcome."""

import enum
import logging
import random
import threading
from collections.abc import Callable, Mapping
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sec_agent.jobs.backoff import retry_delay
from sec_agent.jobs.errors import PermanentJobError
from sec_agent.jobs.heartbeat import Heartbeat
from sec_agent.jobs.models import Job
from sec_agent.jobs.protocol import JobQueue

log = logging.getLogger(__name__)

Handler = Callable[[Job], object]
"""Does the work of one job. Must be idempotent: a job can run more than once."""


class Outcome(enum.Enum):
    DONE = "done"
    RETRY = "retry"
    FAILED = "failed"
    LEASE_LOST = "lease_lost"


class WorkerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner: str = Field(min_length=1)
    lease_seconds: float = Field(default=60.0, gt=0)
    heartbeat_seconds: float = Field(default=20.0, gt=0)
    poll_seconds: float = Field(default=2.0, gt=0)
    backoff_base_seconds: float = Field(default=5.0, gt=0)
    backoff_cap_seconds: float = Field(default=600.0, gt=0)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("heartbeat_seconds must be shorter than lease_seconds")
        if self.backoff_cap_seconds < self.backoff_base_seconds:
            raise ValueError("backoff_cap_seconds must be at least backoff_base_seconds")
        return self


class Worker:
    def __init__(
        self,
        queue: JobQueue,
        handlers: Mapping[str, Handler],
        config: WorkerConfig,
        *,
        rng: random.Random | None = None,
    ) -> None:
        if not handlers:
            raise ValueError("worker has no handlers; it would claim nothing")
        self._queue = queue
        self._handlers = dict(handlers)
        self._config = config
        self._rng = rng or random.Random()

    def run(self, stop: threading.Event | None = None, *, drain: bool = False) -> int:
        """Process jobs until `stop` is set, or, with `drain`, until none is ready.

        Returns how many jobs were processed.
        """
        stop = stop or threading.Event()
        processed = 0
        while not stop.is_set():
            if self.run_once() is not None:
                processed += 1
            elif drain or stop.wait(self._config.poll_seconds):
                break
        return processed

    def run_once(self) -> Outcome | None:
        """Claim and process one job; None when no job was ready."""
        cfg = self._config
        job = self._queue.claim(cfg.owner, self._handlers.keys(), cfg.lease_seconds)
        if job is None:
            return None
        log.info("job %s %s/%s attempt %s", job.id, job.kind, job.key, job.attempts)
        with Heartbeat(
            lambda: self._queue.heartbeat(job, cfg.lease_seconds), cfg.heartbeat_seconds
        ) as beat:
            outcome = self._execute(job)
        if beat.lost:
            outcome = Outcome.LEASE_LOST
        if outcome is Outcome.LEASE_LOST:
            log.warning("job %s: lease lost; another worker owns it now", job.id)
        return outcome

    def _execute(self, job: Job) -> Outcome:
        try:
            self._handlers[job.kind](job)
        except PermanentJobError as error:
            return self._report_failure(job, error, retry=False)
        except Exception as error:
            log.exception("job %s failed", job.id)
            return self._report_failure(job, error, retry=not job.is_final_attempt)
        return Outcome.DONE if self._queue.complete(job) else Outcome.LEASE_LOST

    def _report_failure(self, job: Job, error: Exception, *, retry: bool) -> Outcome:
        message = f"{type(error).__name__}: {error}"
        retry_in = (
            retry_delay(
                job.attempts,
                base=self._config.backoff_base_seconds,
                cap=self._config.backoff_cap_seconds,
                rng=self._rng,
            )
            if retry
            else None
        )
        if not self._queue.fail(job, message, retry_in):
            return Outcome.LEASE_LOST
        return Outcome.RETRY if retry else Outcome.FAILED
