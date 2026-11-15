"""G-ret values: hand-written questions, chunk references, run hits, pool items, labels."""

import datetime as dt
import re
from typing import Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.filings.models import SectionKey

_FROZEN = ConfigDict(frozen=True, extra="forbid")
_DOCID = re.compile(r"^(\d{10}-\d{2}-\d{6})/([a-z_]+)/(\d+)$")
Grade = Literal[0, 1, 2]
"""0 not relevant, 1 partly relevant, 2 answers the question (TREC-style graded relevance)."""


class RetQuestion(BaseModel):
    """A qualitative question, written by hand before reading the filings (gate G-F2)."""

    model_config = _FROZEN

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    ticker: str
    question: str = Field(min_length=1)
    written_on: dt.date


class ChunkRef(BaseModel):
    """A chunk's key inside one index version; `docid` is its TREC document id."""

    model_config = _FROZEN

    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    section: SectionKey
    ordinal: int = Field(ge=0)

    @property
    def docid(self) -> str:
        return f"{self.accession}/{self.section}/{self.ordinal}"

    @classmethod
    def parse(cls, docid: str) -> Self:
        match = _DOCID.fullmatch(docid)
        if match is None or match.group(2) not in get_args(SectionKey):
            raise ValueError(f"bad docid {docid!r}: want accession/section/ordinal")
        return cls.model_validate(
            {"accession": match.group(1), "section": match.group(2), "ordinal": match.group(3)}
        )


class ChunkText(BaseModel):
    model_config = _FROZEN

    cik: str
    text: str
    text_sha256: str


class RunHit(BaseModel):
    """One line of a TREC run: a system's rank for one chunk on one question."""

    model_config = _FROZEN

    qid: str
    chunk: ChunkRef
    rank: int = Field(ge=1)
    score: float
    system: str = Field(min_length=1)


class PoolEntry(BaseModel):
    """A chunk some system ranked in its top k for a question."""

    model_config = _FROZEN

    qid: str
    chunk: ChunkRef
    systems: tuple[str, ...]
    """Systems that ranked it in their top k, sorted. Kept for analysis, never shown."""
    best_rank: int = Field(ge=1)


class PoolItem(PoolEntry):
    """A pool entry with the exact text the labeller sees."""

    ticker: str
    index_version: str
    text: str
    text_sha256: str

    @property
    def docid(self) -> str:
        return self.chunk.docid


class Label(BaseModel):
    """One relevance judgement. Bound to the text's hash: a changed chunk needs a new label."""

    model_config = _FROZEN

    qid: str
    docid: str
    grade: Grade
    text_sha256: str
    labeled_at: dt.datetime
