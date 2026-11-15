"""The queue interface the worker depends on."""

from collections.abc import Collection, Iterable
from typing import Protocol

from sec_agent.jobs.models import Job, JobStatus, NewJob


class JobQueue(Protocol):
    def enqueue(self, jobs: Iterable[NewJob]) -> int:
        """Insert jobs whose (kind, key) is new; return how many were inserted."""
        ...

    def claim(self, owner: str, kinds: Collection[str], lease_seconds: float) -> Job | None:
        """Lease the next ready job of one of `kinds`, or None when there is none."""
        ...

    def heartbeat(self, job: Job, lease_seconds: float) -> bool:
        """Extend the lease; False when it was lost to another worker."""
        ...

    def complete(self, job: Job) -> bool:
        """Mark done; False when the lease was lost (the report is ignored)."""
        ...

    def fail(self, job: Job, error: str, retry_in: float | None) -> bool:
        """Requeue after `retry_in` seconds, or fail for good when it is None."""
        ...

    def counts(self) -> dict[JobStatus, int]:
        """Number of jobs in each status."""
        ...

    def get(self, job_id: int) -> Job | None:
        """One job by id."""
        ...
