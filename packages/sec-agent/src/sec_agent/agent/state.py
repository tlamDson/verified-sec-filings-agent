"""The state LangGraph checkpoints for a conversation. Plain JSON values only, so a
checkpoint written by one version of the code or one replica is read by any other."""

import operator
from typing import Annotated, Any, TypedDict

from sec_agent.llm.messages import Message


class TurnInput(TypedDict):
    """What `ask` writes to start a turn."""

    question: str
    asked_on: str


class AgentState(TypedDict, total=False):
    question: str
    asked_on: str
    """ISO date the current turn was asked on."""
    turn: int
    messages: Annotated[list[Message], operator.add]
    """The whole conversation, append-only: questions, tool calls, tool results, answers."""
    evidence: list[dict[str, Any]]
    """`Evidence` records of the current turn."""
    llm_calls: list[dict[str, Any]]
    """`LLMCall` records of the current turn."""
    status: str | None
    """None while the turn is running."""
    reason: str | None
    text: str | None
