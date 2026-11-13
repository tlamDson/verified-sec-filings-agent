"""What one turn returns: the text, how it ended, and the record behind it.

`evidence` is every tool result of the turn, exactly as the model saw it: the only place
a number in `text` may come from. `llm_calls` says which provider answered each model
call and what it used.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sec_agent.llm.attempts import Attempt

Status = Literal["answered", "step_limit", "degraded"]
Reason = Literal["max_llm_calls", "llm_unavailable", "empty_reply", "truncated_reply"]


class Evidence(BaseModel):
    """One tool call the model made and the result code returned for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    name: str
    arguments: str
    """JSON text as the model wrote it."""
    result: str
    """JSON text as the model was shown it."""
    ok: bool
    trimmed: int = 0


class LLMCall(BaseModel):
    """One model call of the turn. `provider` is None when no provider answered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    attempts: tuple[Attempt, ...]


class Answer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str
    turn: int
    asked_on: dt.date
    status: Status
    reason: Reason | None
    """Why the model's answer is missing; None when `status` is answered."""
    text: str
    """The model's answer, or a fixed notice when it wrote none."""
    evidence: tuple[Evidence, ...]
    llm_calls: tuple[LLMCall, ...]
