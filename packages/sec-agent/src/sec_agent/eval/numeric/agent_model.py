"""b2's chat model: the agent (tools, faithfulness checker) answering one user turn.

Each prompt is its own conversation, so no question sees another's tools or answer. The
recorded output is `Answer.text`, what a user would be shown: a reply line whose value no
tool returned has been withheld by the checker, so it cannot be graded right. A turn that
ended `degraded` (no provider answered) raises instead of being recorded, so an interrupted
night keeps what it finished and resumes later. The record's model name carries the
agent's fingerprint (`eval.fingerprint`), so a cached answer is reused only by the same
agent: prompt, tools, limits and pinned index.
"""

import datetime as dt
import uuid
from collections.abc import Sequence

from sec_agent.agent.service import Agent
from sec_agent.eval.numeric.baselines import Message


class AgentUnavailableError(RuntimeError):
    """No LLM provider answered the agent: stop the run, record nothing for this item."""


class AgentChatModel:
    def __init__(self, agent: Agent, *, name: str, asked_on: dt.date, fingerprint: str) -> None:
        """`name` identifies the agent's model, e.g. "agent:local:qwen", and is recorded as
        "NAME@FINGERPRINT"; `asked_on` is the date relative periods anchor on (E6)."""
        if not fingerprint:
            raise ValueError("an agent answer needs the agent's fingerprint for its cache key")
        self._agent = agent
        self._name = f"{name}@{fingerprint}"
        self._asked_on = asked_on

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: Sequence[Message]) -> str:
        if len(messages) != 1 or messages[0].role != "user":
            raise ValueError("the agent is asked one user message; it keeps its own system prompt")
        thread = f"eval-{uuid.uuid4().hex}"
        answer = self._agent.ask(thread, messages[0].content, asked_on=self._asked_on)
        if answer.status == "degraded":
            raise AgentUnavailableError(f"no LLM provider answered ({answer.reason})")
        return answer.text
