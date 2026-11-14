"""Limits of one turn: how many model calls, how much text in and out."""

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from sec_agent.faithfulness.config import FaithfulnessConfig
from sec_agent.guardrails.config import GuardrailConfig


class AgentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_llm_calls: int = Field(default=6, ge=2)
    """Model calls in one turn. The last one must answer: it is sent with tools switched
    off. At least two, or no tool result could ever be read."""
    max_tool_calls_per_reply: PositiveInt = 8
    """Tool calls run from one reply; the rest are refused without running."""
    max_answer_tokens: PositiveInt = 1024
    """Output limit sent with every model call."""
    max_question_chars: PositiveInt = 2000
    max_history_turns: int = Field(default=4, ge=0)
    """Earlier turns shown to the model, as question and final answer only."""
    faithfulness: FaithfulnessConfig | None = Field(default_factory=FaithfulnessConfig)
    """How the answer is checked against the turn's evidence. None shows the model's
    answer unchecked: the agent-without-checker baseline of N2, never the product."""
    guardrails: GuardrailConfig | None = Field(default_factory=GuardrailConfig)
    """Question screen, passage quarantine, canary, advice filter. None runs none: the
    no-guardrail baseline of S1, never the product."""
