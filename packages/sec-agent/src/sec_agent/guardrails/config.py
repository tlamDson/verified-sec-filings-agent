"""Which guardrails a turn runs. `AgentConfig(guardrails=None)` runs none: the baseline
S1 is measured against, never the product."""

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.guardrails.canary import new_canary


class GuardrailConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    screen_questions: bool = True
    """Refuse a direct attack before any model call; mark requests for advice (E9)."""
    quarantine_passages: bool = True
    """Replace sentences of filing text addressed to an AI before the model reads them."""
    canary: str | None = Field(default_factory=new_canary, min_length=12)
    """The secret of the system prompt; None leaves it out. Random per configuration, so
    per replica: a leak is checked against the canary the same replica sent."""
    filter_advice: bool = True
    """Drop advice sentences from the answer and add the disclaimer."""
