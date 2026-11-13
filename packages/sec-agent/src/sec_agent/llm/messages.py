"""Chat messages, tool calls and completions in the OpenAI chat shape, as plain data.

Messages are dicts so they go to a provider, and into a checkpoint, without conversion.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict

Role = Literal["system", "user", "assistant", "tool"]
ToolChoice = Literal["auto", "none"]


class FunctionCall(TypedDict):
    name: str
    arguments: str
    """JSON text exactly as the model wrote it; the tool runner validates it."""


class ToolCall(TypedDict):
    id: str
    type: Literal["function"]
    function: FunctionCall


class Message(TypedDict):
    role: Role
    content: str | None
    tool_calls: NotRequired[list[ToolCall]]
    tool_call_id: NotRequired[str]


class FunctionSchema(TypedDict):
    name: str
    description: str
    parameters: dict[str, Any]


class ToolSchema(TypedDict):
    type: Literal["function"]
    function: FunctionSchema


@dataclass(frozen=True)
class Usage:
    """Token counts as a provider reported them; a count it left out is 0."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int = 0
    """The provider's own total: some count tokens (hidden reasoning) in neither part."""

    @property
    def total(self) -> int:
        """The most the reported counts come to."""
        return max(self.total_tokens, self.prompt_tokens + self.completion_tokens)

    @property
    def complete(self) -> bool:
        """Whether both parts were reported. Only then is `total` what the call used;
        otherwise it is a floor, and the call may have used far more."""
        return self.prompt_tokens > 0 and self.completion_tokens > 0


@dataclass(frozen=True)
class ChatRequest:
    messages: Sequence[Message]
    tools: Sequence[ToolSchema] = ()
    tool_choice: ToolChoice = "auto"
    max_tokens: int | None = None
    temperature: float = 0.0


@dataclass(frozen=True)
class Completion:
    message: Message
    finish_reason: str
    usage: Usage
    model: str


def system(text: str) -> Message:
    return {"role": "system", "content": text}


def user(text: str) -> Message:
    return {"role": "user", "content": text}


def assistant(text: str) -> Message:
    return {"role": "assistant", "content": text}


def tool_result(call_id: str, content: str) -> Message:
    return {"role": "tool", "content": content, "tool_call_id": call_id}
