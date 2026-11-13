"""Values of the retrieval index: embedding model settings, spaces, filters, hits, snapshots."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sec_agent.edgar.urls import normalize_cik
from sec_agent.filings.models import FilingForm, SectionKey

_FROZEN = ConfigDict(frozen=True, extra="forbid")

SearchMode = Literal["dense", "lexical", "hybrid"]

MAX_HNSW_DIMENSIONS = 2000  # pgvector: an HNSW index on `vector` holds up to 2,000 dims


class EmbedderSpec(BaseModel):
    """Everything about the embedding model that changes the vectors it returns."""

    model_config = _FROZEN

    model: str = Field(min_length=1)  # Hugging Face id, e.g. "BAAI/bge-base-en-v1.5"
    dimensions: int = Field(ge=1, le=MAX_HNSW_DIMENSIONS)
    normalized: bool
    query_prefix: str = ""
    passage_prefix: str = ""
    max_input_tokens: int | None = Field(default=None, ge=1)  # longer passages are truncated


class EmbeddingSpace(BaseModel):
    """One chunk build (`index_version`) embedded by one model: the unit a query pins."""

    model_config = _FROZEN

    name: str
    index_version: str
    spec: EmbedderSpec


class SearchFilters(BaseModel):
    """Restrict a search to some companies, forms, sections, or report dates (inclusive)."""

    model_config = _FROZEN

    ciks: tuple[str, ...] = ()
    forms: tuple[FilingForm, ...] = ()
    sections: tuple[SectionKey, ...] = ()
    report_from: dt.date | None = None
    report_to: dt.date | None = None

    @field_validator("ciks", mode="before")
    @classmethod
    def _ciks(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            items: list[object] = list(value)  # pyright: ignore[reportUnknownArgumentType]
            return tuple(normalize_cik(v) if isinstance(v, int | str) else v for v in items)
        return value

    @property
    def is_empty(self) -> bool:
        return self == SearchFilters()


class Hit(BaseModel):
    """One retrieved passage, with what a citation needs.

    `score` is the ranking score of the mode: cosine similarity (dense), BM25 (lexical), or
    the RRF sum (hybrid). The per-arm ranks and raw scores are kept beside it.
    """

    model_config = _FROZEN

    rank: int = Field(ge=1)
    score: float
    dense_rank: int | None
    lexical_rank: int | None
    distance: float | None  # cosine distance, dense arm
    bm25: float | None  # BM25 score, lexical arm
    index_version: str
    accession: str
    section: SectionKey
    ordinal: int
    cik: str
    form: FilingForm
    filing_date: dt.date
    report_date: dt.date
    char_start: int
    char_end: int
    text: str
    source_url: str


class BuildReport(BaseModel):
    """What one `build_index` run found and did. Counts, never hidden."""

    model_config = _FROZEN

    index_version: str
    space: str
    chunks: int  # chunks of the version
    embedded: int  # embedded by this run
    already_embedded: int
    truncated: int  # passages this run embedded that exceed the model's input limit
    lexical_rows: int  # chunks with a lexical row after this run


class Snapshot(BaseModel):
    """A named, verified state of one embedding space. Eval runs pin to one."""

    model_config = _FROZEN

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
    space: str
    index_version: str
    spec: EmbedderSpec
    chunk_count: int = Field(ge=0)
    filing_count: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: dt.datetime

    @property
    def embedding_space(self) -> EmbeddingSpace:
        return EmbeddingSpace(name=self.space, index_version=self.index_version, spec=self.spec)
