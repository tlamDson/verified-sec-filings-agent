"""Reading a turn's server-sent events into a `TurnOutcome`.

The driver is a client of the web app, so it reads only the answer fields it needs and
ignores the rest; an answer it cannot read is an `error`, never a guess.
"""

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from sec_agent.agent.answer import Status
from sec_agent.faithfulness.models import Verdict
from sec_agent.simusers.outcome import TurnOutcome

_LOOSE = ConfigDict(frozen=True, extra="ignore")


class _Check(BaseModel):
    model_config = _LOOSE

    verdict: Verdict
    removed: int


class _Answer(BaseModel):
    model_config = _LOOSE

    turn: int
    status: Status
    cards: tuple[Any, ...]
    citations: tuple[Any, ...]
    check: _Check | None


def sse_events(lines: Iterable[str]) -> list[tuple[str, str]]:
    """(event, data) pairs of a stream of lines; a frame ends at a blank line."""
    found: list[tuple[str, str]] = []
    name, data = "message", ""
    for line in lines:
        if line == "":
            if data:
                found.append((name, data))
            name, data = "message", ""
        elif line.startswith("event:"):
            name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data += line.removeprefix("data:").strip()
    if data:
        found.append((name, data))
    return found


def outcome_of(events: Iterable[tuple[str, str]], seconds: float) -> TurnOutcome:
    for name, data in events:
        if name != "answer":
            continue
        try:
            answer = _Answer.model_validate(json.loads(data))
        except (ValueError, ValidationError):
            break
        return TurnOutcome(
            kind=answer.status,
            turn=answer.turn,
            verdict=answer.check.verdict if answer.check else None,
            removed=answer.check.removed if answer.check else 0,
            evidence=len(answer.cards) + len(answer.citations),
            seconds=seconds,
        )
    return TurnOutcome(kind="error", seconds=seconds)
