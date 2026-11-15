"""Test doubles for the LLM router. Pytest puts this directory on sys.path (`pythonpath`).

`ScriptedProvider` is a **simulated model**: every reply is written by the test. No model is
called and nothing here measures a real model.
"""

import datetime as dt
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from sec_agent.llm.messages import ChatRequest, Completion, Message, ToolCall, Usage
from sec_agent.llm.quota import QuotaLimits

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "llm"
T0 = dt.datetime(2026, 11, 13, 9, 30, 15, tzinfo=dt.UTC)

Reply = Message | Exception | Callable[[ChatRequest], Message]


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text("utf-8"))


def says(text: str) -> Message:
    """A simulated reply with text and no tool call."""
    return {"role": "assistant", "content": text}


def call(name: str, call_id: str = "c1", **arguments: object) -> ToolCall:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def calls(*tool_calls: ToolCall) -> Message:
    """A simulated reply that only calls tools."""
    return {"role": "assistant", "content": None, "tool_calls": list(tool_calls)}


class ScriptedProvider:
    """Replies from a script, in order; an exception in the script is raised instead."""

    def __init__(
        self,
        name: str,
        replies: Iterable[Reply] = (),
        *,
        limits: QuotaLimits | None = None,
        usage: Usage | None = None,
        finish_reason: str | None = None,
    ) -> None:
        self._name = name
        self._limits = limits or QuotaLimits()
        self._replies = list(replies)
        self._usage = usage or Usage(prompt_tokens=100, completion_tokens=10)
        self._finish_reason = finish_reason
        self.requests: list[ChatRequest] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def limits(self) -> QuotaLimits:
        return self._limits

    def then(self, *replies: Reply) -> None:
        self._replies.extend(replies)

    def complete(self, request: ChatRequest) -> Completion:
        self.requests.append(request)
        if not self._replies:
            raise AssertionError(f"provider {self._name}: the script has no reply left")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = reply(request) if callable(reply) else reply
        finish = self._finish_reason or ("tool_calls" if message.get("tool_calls") else "stop")
        return Completion(
            message=message, finish_reason=finish, usage=self._usage, model=f"sim-{self._name}"
        )


class Clock:
    """A monotonic clock and a wall clock that move only when a test says so."""

    def __init__(self, start: dt.datetime = T0) -> None:
        self._start = start
        self.seconds = 0.0

    def advance(self, seconds: float) -> None:
        self.seconds += seconds

    def monotonic(self) -> float:
        return self.seconds

    def now(self) -> dt.datetime:
        return self._start + dt.timedelta(seconds=self.seconds)
