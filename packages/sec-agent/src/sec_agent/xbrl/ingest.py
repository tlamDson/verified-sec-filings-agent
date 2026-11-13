"""The `xbrl.companyfacts` job: one company's companyfacts -> its facts in one snapshot.

Key `<index_version>:<CIK>`, so each index_version ingests each company once. The handler
fetches through the EDGAR client (rate limit, User-Agent, raw cache), normalises, and
upserts in one transaction, so running it twice has the effect of running it once.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from sec_agent.edgar.errors import EdgarNotFoundError
from sec_agent.edgar.urls import companyfacts_url, normalize_cik
from sec_agent.jobs.errors import PermanentJobError
from sec_agent.jobs.models import Job, NewJob
from sec_agent.jobs.worker import Handler
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize
from sec_agent.xbrl.store import FactWriter

KIND = "xbrl.companyfacts"

Fetch = Callable[[str, bool], bytes]
"""(url, refresh) -> body; in production `EdgarClient.get`."""


class CompanyFactsPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cik: str
    index_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    refresh: bool = False
    """Bypass the raw cache: use it when building a new index_version from fresh data."""

    @field_validator("cik", mode="before")
    @classmethod
    def _cik(cls, value: object) -> str:
        if not isinstance(value, int | str):
            raise ValueError("CIK must be an int or a digit string")
        return normalize_cik(value)


def companyfacts_job(cik: int | str, index_version: str, *, refresh: bool = False) -> NewJob:
    """The job that ingests one company into `index_version`. Raises ValueError on bad input."""
    payload = CompanyFactsPayload(cik=str(cik), index_version=index_version, refresh=refresh)
    return NewJob(
        kind=KIND,
        key=f"{payload.index_version}:{payload.cik}",
        payload=payload.model_dump(),
    )


def make_handler(
    fetch: Fetch, open_store: Callable[[], AbstractContextManager[FactWriter]]
) -> Handler:
    def handle(job: Job) -> int:
        try:
            payload = CompanyFactsPayload.model_validate(job.payload)
        except ValidationError as error:
            raise PermanentJobError(f"bad {KIND} payload: {error}") from error
        url = companyfacts_url(payload.cik)
        try:
            body = fetch(url, payload.refresh)
        except EdgarNotFoundError as error:
            raise PermanentJobError(f"no XBRL companyfacts on EDGAR: {error}") from error
        try:
            doc = parse_companyfacts(body)
        except ValueError as error:  # ValidationError is a ValueError
            raise PermanentJobError(f"malformed companyfacts at {url}: {error}") from error
        if doc.cik != int(payload.cik):
            raise PermanentJobError(f"{url} holds CIK {doc.cik}, not {payload.cik}")
        normalized = normalize(doc)
        with open_store() as store:
            return store.write(
                index_version=payload.index_version,
                cik=doc.cik,
                entity_name=doc.entity_name,
                normalized=normalized,
            )

    return handle
