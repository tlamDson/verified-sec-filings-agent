"""G-judge files: the blind items a rater or judge sees, the hidden key, labels, verdicts.

`items.jsonl` (BlindItem) is all a rater or a judge is given: the question turns, the
date asked, the answer text and the sources the answering system itself retrieved. It
never names the system or its model, the code grader's verdict, the stratum or the gold
answer. `key.jsonl` (KeyEntry) maps each opaque id back to its origin and is read only
by the scorer. A label (`labels.jsonl`) and a verdict (`<judge>.jsonl`) are one row per
item id: `correct` means the answer is right, for the right period, and every figure is
supported by a cited source (or, without sources, by the filing itself).
"""

import datetime as dt
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

Stratum = Literal["correct", "wrong_number", "wrong_period", "citation"]
STRATA: tuple[Stratum, ...] = get_args(Stratum)
Origin = Literal["numeric", "agent"]
VerdictValue = Literal["correct", "incorrect"]
LabelValue = Literal["correct", "incorrect", "unsure"]
ITEM_ID = r"^gj-[0-9a-z]{12}$"

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Source(BaseModel):
    """One tool call the answering system made, and the result it was shown."""

    model_config = _FROZEN

    tool: str
    arguments: str
    result: str


class BlindItem(BaseModel):
    model_config = _FROZEN

    id: str = Field(pattern=ITEM_ID)
    turns: tuple[str, ...] = Field(min_length=1)
    """The user's turns; the answer replies to the last one."""
    asked_on: dt.date | None
    """The date relative periods ("last quarter") are anchored to (E6), when recorded."""
    answer: str
    sources: tuple[Source, ...]


class Candidate(BaseModel):
    """One committed answer before sampling: the blind content and what the key keeps."""

    model_config = _FROZEN

    origin: Origin
    record_id: str
    system: str
    model: str
    stratum: Stratum
    grader_error: str | None
    turns: tuple[str, ...] = Field(min_length=1)
    asked_on: dt.date | None
    answer: str
    sources: tuple[Source, ...]


class KeyEntry(BaseModel):
    model_config = _FROZEN

    id: str = Field(pattern=ITEM_ID)
    origin: Origin
    record_id: str
    system: str
    model: str
    stratum: Stratum
    grader_error: str | None
    grader_verdict: VerdictValue


class Label(BaseModel):
    """A blind label. `rater` says who made it, e.g. "codex-rater, owner-checked"."""

    model_config = _FROZEN

    id: str = Field(pattern=ITEM_ID)
    label: LabelValue
    rater: str = Field(min_length=1)
    note: str = ""


class Verdict(BaseModel):
    model_config = _FROZEN

    id: str = Field(pattern=ITEM_ID)
    verdict: VerdictValue
    judge: str = Field(min_length=1)
