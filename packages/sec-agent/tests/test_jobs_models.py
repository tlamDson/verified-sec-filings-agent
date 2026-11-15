"""Job values: validation of new jobs and the lease a claimed job carries."""

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from sec_agent.jobs.models import Job, NewJob


def _job(**overrides: object) -> Job:
    now = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    fields: dict[str, object] = {
        "id": 1,
        "kind": "xbrl.companyfacts",
        "key": "0000320193",
        "payload": {},
        "status": "running",
        "attempts": 1,
        "max_attempts": 5,
        "run_after": now,
        "lease_owner": "w1",
        "lease_token": uuid.uuid4(),
        "lease_expires_at": now,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
    }
    fields.update(overrides)
    return Job.model_validate(fields)


def test_new_job_defaults() -> None:
    job = NewJob(kind="filing.sections", key="0000320193-24-000123")
    assert job.payload == {}
    assert job.max_attempts == 5


@pytest.mark.parametrize("kind", ["", "Upper", "has space", "1starts.with.digit"])
def test_new_job_rejects_bad_kind(kind: str) -> None:
    with pytest.raises(ValidationError):
        NewJob(kind=kind, key="k")


def test_new_job_rejects_empty_key_and_zero_attempts() -> None:
    with pytest.raises(ValidationError):
        NewJob(kind="k", key="")
    with pytest.raises(ValidationError):
        NewJob(kind="k", key="x", max_attempts=0)


def test_require_lease_returns_token_of_claimed_job() -> None:
    token = uuid.uuid4()
    assert _job(lease_token=token).require_lease() == token


def test_require_lease_rejects_job_without_lease() -> None:
    with pytest.raises(ValueError, match="no lease"):
        _job(status="queued", lease_token=None).require_lease()


def test_is_final_attempt() -> None:
    assert not _job(attempts=4, max_attempts=5).is_final_attempt
    assert _job(attempts=5, max_attempts=5).is_final_attempt
