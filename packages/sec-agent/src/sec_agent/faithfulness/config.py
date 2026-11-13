"""When a failed sentence is dropped and when the whole answer is blocked."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FaithfulnessConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    on_failure: Literal["drop", "block"] = "drop"
    """drop: remove each failed sentence and say so; block: any failure blocks."""
    max_dropped_share: float = Field(default=0.5, ge=0.0, le=1.0)
    """Block when more than this share of the checked sentences (those holding a figure,
    a date or a citation) fail. Blocked too when nothing would be left to show."""
