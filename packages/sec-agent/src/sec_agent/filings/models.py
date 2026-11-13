"""Values of the filing text index: a filing, its sections, its chunks, and the job payload."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sec_agent.edgar.urls import archive_url, normalize_cik
from sec_agent.jobs.models import NewJob

FILING_SECTIONS_KIND = "filing.sections"

FilingForm = Literal["10-K", "10-K/A", "10-Q", "10-Q/A"]
TEXT_FORMS: frozenset[str] = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})

SectionKey = Literal["business", "risk_factors", "mdna", "market_risk"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class FilingRef(BaseModel):
    """One 10-K or 10-Q filing and its primary HTML document on EDGAR."""

    model_config = _FROZEN

    cik: str
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: FilingForm
    filing_date: dt.date
    report_date: dt.date
    primary_document: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*\.html?$")

    @field_validator("cik", mode="before")
    @classmethod
    def _cik(cls, value: object) -> str:
        if not isinstance(value, int | str):
            raise ValueError(f"CIK must be an int or a digit string, got {value!r}")
        return normalize_cik(value)

    @property
    def document_url(self) -> str:
        return archive_url(self.cik, self.accession, self.primary_document)


class Section(BaseModel):
    """One item of a filing. `text` is its body without the heading; lines are blocks."""

    model_config = _FROZEN

    key: SectionKey
    item: str  # "Item 1A", "Part II, Item 1A"
    heading: str  # the heading as the filing writes it
    text: str
    token_count: int = Field(ge=0)


class Chunk(BaseModel):
    """A passage of a section, with the metadata retrieval filters and citations need.

    `section_text[char_start:char_end] == text`, so a citation can point at the exact span.
    """

    model_config = _FROZEN

    index_version: str
    accession: str
    cik: str
    form: FilingForm
    filing_date: dt.date
    report_date: dt.date
    section: SectionKey
    ordinal: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    token_count: int = Field(gt=0)
    text: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IndexedFiling(BaseModel):
    """Everything one filing contributes to one index version."""

    model_config = _FROZEN

    index_version: str
    filing: FilingRef
    sections: tuple[Section, ...]
    chunks: tuple[Chunk, ...]


class FilingJob(BaseModel):
    """Payload of a `filing.sections` job: which filing, for which index version."""

    model_config = _FROZEN

    index_version: str = Field(min_length=1)
    filing: FilingRef

    def to_new_job(self) -> NewJob:
        # The version is part of the key: a new index_version is a new set of jobs, built
        # beside the old index (blue/green) instead of overwriting it.
        return NewJob(
            kind=FILING_SECTIONS_KIND,
            key=f"{self.index_version}/{self.filing.accession}",
            payload=self.model_dump(mode="json"),
        )
