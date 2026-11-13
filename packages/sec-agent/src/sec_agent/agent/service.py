"""Agent: one turn of a conversation.

`ask` validates the question, runs the turn graph (`graph`) under the conversation's
`thread_id`, and returns the `Answer`; `steps` runs the same turn and yields each tool
result as it arrives, then the `Answer`. An `Agent` is pinned to the index versions of
its `ToolRunner`: build a new one when the index pointer moves.
"""

import datetime as dt
from collections.abc import Iterator
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver

from sec_agent.agent.answer import Answer, Evidence, LLMCall
from sec_agent.agent.config import AgentConfig
from sec_agent.agent.errors import InvalidQuestionError, InvalidThreadError
from sec_agent.agent.graph import build_turn_graph
from sec_agent.agent.nodes import TurnNodes
from sec_agent.agent.state import AgentState, TurnInput
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.faithfulness.models import FaithfulnessReport
from sec_agent.llm.router import LLMRouter

MAX_THREAD_ID_CHARS = 200


class Agent:
    def __init__(
        self,
        *,
        router: LLMRouter,
        tools: ToolRunner,
        checkpointer: BaseCheckpointSaver[Any],
        config: AgentConfig | None = None,
    ) -> None:
        self._config = config or AgentConfig()
        nodes = TurnNodes(router, tools, self._config)
        self._run, self._steps = build_turn_graph(nodes, checkpointer)

    def ask(self, thread_id: str, question: str, *, asked_on: dt.date) -> Answer:
        """Run one turn of conversation `thread_id` and return how it ended.

        `asked_on` is the user's date: relative periods in the question anchor on it (E6).
        Raises `ConversationConflictError` when another request advanced the conversation
        while this one ran; nothing of this turn is kept past that point.
        """
        thread, turn = self._turn(thread_id, question, asked_on)
        return _answer(thread, asked_on, self._run(thread, turn, self._step_limit))

    def steps(
        self, thread_id: str, question: str, *, asked_on: dt.date
    ) -> Iterator[Evidence | Answer]:
        """Run one turn like `ask`, yielding each tool result when its step ends and the
        `Answer` last. Nothing runs until the first item is asked for."""
        thread, turn = self._turn(thread_id, question, asked_on)
        seen = 0
        state: AgentState = {}
        for state in self._steps(thread, turn, self._step_limit):
            evidence = state.get("evidence", [])
            for record in evidence[seen:]:
                yield Evidence.model_validate(record)
            seen = len(evidence)
        yield _answer(thread, asked_on, state)

    @property
    def _step_limit(self) -> int:
        return 2 * self._config.max_llm_calls + 4

    def _turn(self, thread_id: str, question: str, asked_on: dt.date) -> tuple[str, TurnInput]:
        thread = _thread_id(thread_id)
        turn: TurnInput = {
            "question": _question(question, self._config.max_question_chars),
            "asked_on": asked_on.isoformat(),
        }
        return thread, turn


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
    report = state.get("faithfulness")
    return Answer(
        thread_id=thread_id,
        turn=state.get("turn", 0),
        asked_on=asked_on,
        status=cast(Any, state.get("status")),
        reason=cast(Any, state.get("reason")),
        text=state.get("text") or "",
        draft=state.get("draft"),
        faithfulness=None if report is None else FaithfulnessReport.model_validate(report),
        evidence=tuple(Evidence.model_validate(e) for e in state.get("evidence", [])),
        llm_calls=tuple(LLMCall.model_validate(c) for c in state.get("llm_calls", [])),
    )
