"""One turn as a stream of server-sent events.

The agent's steps are forwarded as they happen: each tool result as cards and citations,
then the answer the faithfulness checker passed. When the turn ends degraded with no
tool result to show (no model was reachable to pick a tool), the figures the question
asks for are looked up by rules (`sec_agent.degraded`) and shown the same way. The turn
is logged with its cohort before the answer is sent, so feedback can always find it.

A user's conversation is kept under `<user id>:<thread id>`: two users who send the same
thread id never read or advance each other's conversation.
"""

import datetime as dt
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from sec_agent.agent.answer import Answer, Evidence
from sec_agent.agent.errors import AgentError, ConversationConflictError
from sec_agent.api.charts import charts_of
from sec_agent.api.events import (
    AnswerPayload,
    CheckSummary,
    ErrorCode,
    ErrorPayload,
    TurnStarted,
    Usage,
)
from sec_agent.api.identity import Identity
from sec_agent.api.present import present
from sec_agent.api.sse import sse_event
from sec_agent.api.store import ApiStore, TurnRecord
from sec_agent.degraded.lookup import Tools, deterministic_evidence
from sec_agent.tools.companies import CompanyDirectory

_LOG = logging.getLogger(__name__)
_MESSAGES: dict[ErrorCode, str] = {
    "conversation_conflict": (
        "This conversation was continued from another window. Reload it and ask again."
    ),
    "invalid_request": "The question could not be accepted as sent.",
    "internal_error": "Something went wrong while answering. Please ask again.",
}


class TurnAgent(Protocol):
    def steps(
        self, thread_id: str, question: str, *, asked_on: dt.date
    ) -> Iterator[Evidence | Answer]: ...


@dataclass(frozen=True)
class TurnRequest:
    identity: Identity
    thread_id: str
    question: str
    asked_on: dt.date
    """The date relative periods anchor on (E6)."""
    asked_at: dt.datetime
    usage: Usage


class TurnStreamer:
    def __init__(
        self, *, agent: TurnAgent, tools: Tools, companies: CompanyDirectory, store: ApiStore
    ) -> None:
        self._agent = agent
        self._tools = tools
        self._companies = companies
        self._store = store

    def stream(self, request: TurnRequest) -> Iterator[bytes]:
        started = TurnStarted(
            thread_id=request.thread_id, cohort=request.identity.cohort, usage=request.usage
        )
        yield sse_event("turn", started)
        try:
            yield from self._turn(request)
        except ConversationConflictError:
            yield _error("conversation_conflict")
        except AgentError:
            yield _error("invalid_request")
        except Exception:  # the status line is already sent: the stream must end in an event
            _LOG.exception("turn failed")
            yield _error("internal_error")

    def _turn(self, request: TurnRequest) -> Iterator[bytes]:
        answer: Answer | None = None
        steps = self._agent.steps(
            f"{request.identity.user_id}:{request.thread_id}",
            request.question,
            asked_on=request.asked_on,
        )
        for step in steps:
            if isinstance(step, Answer):
                answer = step
            else:
                yield from _evidence_event([step])
        if answer is None:
            raise RuntimeError("the agent ended a turn without an answer")
        evidence = list(answer.evidence)
        degraded = answer.status == "degraded"
        if degraded and not any(item.ok for item in evidence):
            looked_up = deterministic_evidence(
                request.question,
                tools=self._tools,
                companies=self._companies,
                asked_on=request.asked_on,
            )
            yield from _evidence_event(looked_up)
            evidence.extend(looked_up)
        view = present(evidence)
        self._store.record_turn(
            TurnRecord(
                user_id=request.identity.user_id,
                cohort=request.identity.cohort,
                thread_id=request.thread_id,
                turn=answer.turn,
                asked_at=request.asked_at,
                status=answer.status,
                degraded=degraded,
            )
        )
        report = answer.faithfulness
        payload = AnswerPayload(
            thread_id=request.thread_id,
            turn=answer.turn,
            status=answer.status,
            reason=answer.reason,
            degraded=degraded,
            text=answer.text,
            cards=view.cards,
            citations=view.citations,
            charts=charts_of(view.cards),
            check=None if report is None else CheckSummary.of(report),
        )
        yield sse_event("answer", payload)


def _evidence_event(evidence: tuple[Evidence, ...] | list[Evidence]) -> Iterator[bytes]:
    view = present(evidence)
    if view.cards or view.citations:
        yield sse_event("evidence", view)


def _error(code: ErrorCode) -> bytes:
    return sse_event("error", ErrorPayload(code=code, message=_MESSAGES[code]))
