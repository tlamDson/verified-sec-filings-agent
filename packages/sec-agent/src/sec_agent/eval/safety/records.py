"""SafetyRecord: one G-red item run through one system, as `runner` appends it."""

from pydantic import BaseModel, ConfigDict

from sec_agent.golden.gred.models import RedKind


class SafetyRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    kind: RedKind
    system: str
    """`guarded` (the product) or `none` (no guardrails), or another configuration."""
    status: str
    reason: str | None
    text: str
    """What the user was shown."""
    attack_succeeded: bool | None
    exposed: bool
    refused: bool
    llm_calls: int
    model: str | None = None
    """The model that wrote the last reply; None when none was called."""
    question_screen: str | None = None
    flagged_passages: int = 0
    advice_dropped: int = 0
