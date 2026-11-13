"""What the checker found: each mention, what it traced to, and what the user is shown."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.faithfulness.scan import DateMention, NumberMention

_FROZEN = ConfigDict(frozen=True, extra="forbid")

MentionStatus = Literal["traced", "wrong_period", "uncited", "wrong_unit", "untraced"]
"""traced: a source has this value, unit and period. wrong_period: the value and unit of
a source for another period than the sentence names (E1). uncited: the number of a
passage the sentence does not cite. wrong_unit: a source's value in another unit (E5).
untraced: no source holds it."""
CitationStatus = Literal["valid", "unknown"]
Verdict = Literal["pass", "trimmed", "blocked"]


class SourceRef(BaseModel):
    """Where a mention was found: a field of one tool result, or the day asked."""

    model_config = _FROZEN

    call_id: str | None
    tool: str | None
    field: str
    """Path in the result, e.g. "fact.value", "rows[1].rank", "passages[0].text"."""
    citation: str | None = None
    """The citation key the sentence gave for a passage figure."""


class MentionCheck(BaseModel):
    model_config = _FROZEN

    mention: Annotated[NumberMention | DateMention, Field(discriminator="kind")]
    status: MentionStatus
    source: SourceRef | None
    """The source it traced to; for a near miss, the source it missed."""


class CitationCheck(BaseModel):
    model_config = _FROZEN

    key: str
    start: int
    end: int
    status: CitationStatus


class SentenceCheck(BaseModel):
    model_config = _FROZEN

    start: int
    end: int
    text: str
    mentions: tuple[MentionCheck, ...]
    citations: tuple[CitationCheck, ...]
    passed: bool
    """Every mention traced and every citation names a source of the turn."""
    kept: bool
    """Shown to the user."""


class FaithfulnessReport(BaseModel):
    model_config = _FROZEN

    verdict: Verdict
    text: str
    """What the user is shown: the draft, the draft without its failed sentences and a
    note, or the blocked notice."""
    sentences: tuple[SentenceCheck, ...]
    mentions: int
    traced: int
    faithful: bool
    """N2 for one answer: every figure and date traced, every citation valid."""
