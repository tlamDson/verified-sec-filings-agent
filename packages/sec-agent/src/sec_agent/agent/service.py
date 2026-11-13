"""Agent: one turn of a conversation.

`ask` validates the question, runs the turn graph (`graph`) under the conversation's
`thread_id`, and returns the `Answer`. An `Agent` is pinned to the index versions of its
`ToolRunner`: build a new one when the index pointer moves.
"""

import datetime as dt
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from opentelemetry.trace import Tracer

from sec_agent.agent.answer import Answer, Evidence, LLMCall
from sec_agent.agent.config import AgentConfig
from sec_agent.agent.errors import InvalidQuestionError, InvalidThreadError
from sec_agent.agent.graph import build_turn_runner
from sec_agent.agent.nodes import TurnNodes
from sec_agent.agent.state import AgentState, TurnInput
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.llm.router import LLMRouter
from sec_agent.observability.spans import default_tracer, turn_ended, turn_span

MAX_THREAD_ID_CHARS = 200


class Agent:
    def __init__(
        self,
        *,
        router: LLMRouter,
        tools: ToolRunner,
        checkpointer: BaseCheckpointSaver[Any],
        config: AgentConfig | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        """`tracer` defaults to the process's (`observability.setup.tracing`); each turn is
        one trace. Give the router the same tracer, so its provider calls join the turn."""
        self._config = config or AgentConfig()
        self._tracer = tracer or default_tracer()
        nodes = TurnNodes(router, tools, self._config, self._tracer)
        self._run = build_turn_runner(nodes, checkpointer)

    def ask(self, thread_id: str, question: str, *, asked_on: dt.date) -> Answer:
        """Run one turn of conversation `thread_id` and return how it ended.

        `asked_on` is the user's date: relative periods in the question anchor on it (E6).
        Raises `ConversationConflictError` when another request advanced the conversation
        while this one ran; nothing of this turn is kept past that point.
        """
        thread = _thread_id(thread_id)
        turn: TurnInput = {
            "question": _question(question, self._config.max_question_chars),
            "asked_on": asked_on.isoformat(),
        }
        with turn_span(self._tracer, thread) as span:
            state = self._run(thread, turn, 2 * self._config.max_llm_calls + 4)
            answer = _answer(thread, asked_on, state)
            turn_ended(span, turn=answer.turn, status=answer.status, reason=answer.reason)
        return answer


def _thread_id(thread_id: str) -> str:
    if not thread_id.strip():
        raise InvalidThreadError("the conversation id is empty")
    if len(thread_id) > MAX_THREAD_ID_CHARS or not thread_id.isprintable():
        raise InvalidThreadError(
            f"the conversation id must be at most {MAX_THREAD_ID_CHARS} printable characters"
        )
    return thread_id


def _question(question: str, max_chars: int) -> str:
    text = question.strip()
    if not text:
        raise InvalidQuestionError("the question is empty")
    if len(text) > max_chars:
        raise InvalidQuestionError(f"the question is longer than {max_chars} characters")
    return text


def _answer(thread_id: str, asked_on: dt.date, state: AgentState) -> Answer:
    return Answer(
        thread_id=thread_id,
        turn=state.get("turn", 0),
        asked_on=asked_on,
        status=cast(Any, state.get("status")),
        reason=cast(Any, state.get("reason")),
        text=state.get("text") or "",
        evidence=tuple(Evidence.model_validate(e) for e in state.get("evidence", [])),
        llm_calls=tuple(LLMCall.model_validate(c) for c in state.get("llm_calls", [])),
    )
