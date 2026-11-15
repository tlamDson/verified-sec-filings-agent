"""Job values: what a scheduler enqueues and what a worker claims."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

JobStatus = Literal["queued", "running", "done", "failed"]
JOB_STATUSES: tuple[JobStatus, ...] = ("queued", "running", "done", "failed")


class NewJob(BaseModel):
    """A job to enqueue. `(kind, key)` is unique: enqueueing it twice is a no-op."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
    key: str = Field(min_length=1)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    max_attempts: int = Field(default=5, ge=1)


class Job(BaseModel):
    """One row of the `jobs` table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    kind: str
    key: str
    payload: dict[str, JsonValue]
    status: JobStatus
    attempts: int
    max_attempts: int
    run_after: dt.datetime
    lease_owner: str | None
    lease_token: uuid.UUID | None
    lease_expires_at: dt.datetime | None
    last_error: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    finished_at: dt.datetime | None

    def require_lease(self) -> uuid.UUID:
        """The fencing token of this claim; every report back to the queue must carry it."""
        if self.lease_token is None:
            raise ValueError(f"job {self.id} has no lease; claim it first")
        return self.lease_token

    @property
    def is_final_attempt(self) -> bool:
        return self.attempts >= self.max_attempts
