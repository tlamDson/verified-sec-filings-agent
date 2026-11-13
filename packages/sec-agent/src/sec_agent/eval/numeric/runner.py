"""Run a numeric system over G-num questions, one results file per system.

Each answer is appended (and flushed) as soon as it arrives, so an interrupted night keeps
what it finished. A rerun asks only questions whose (question, model, prompt hash) has no
record yet: changing the model or the prompt (or the retrieved passages) asks again, the
rest costs nothing. The raw output is stored; grading reads it later, so a grading fix
never needs the model again.
"""

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.eval.numeric.baselines import ChatModel, Message, NumericSystem
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.jsonl import append_jsonl, read_jsonl


class AnswerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    qid: str
    system: str
    model: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output: str
    answered_at: dt.datetime


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asked: int
    cached: int


def prompt_sha256(messages: Sequence[Message]) -> str:
    payload = json.dumps([m.model_dump() for m in messages], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_numeric(
    questions: Sequence[NumQuestion],
    system: NumericSystem,
    model: ChatModel,
    *,
    results: Path,
    now: Callable[[], dt.datetime],
) -> RunSummary:
    existing = read_jsonl(results, AnswerRecord)
    others = sorted({r.system for r in existing} - {system.name})
    if others:
        raise ValueError(f"{results} holds answers of {others}, not of {system.name}")
    done = {(r.qid, r.model, r.prompt_sha256) for r in existing}
    asked = cached = 0
    for question in questions:
        messages = system.prompt(question)
        digest = prompt_sha256(messages)
        if (question.id, model.name, digest) in done:
            cached += 1
            continue
        output = model.complete(messages)
        record = AnswerRecord(
            qid=question.id,
            system=system.name,
            model=model.name,
            prompt_sha256=digest,
            output=output,
            answered_at=now(),
        )
        append_jsonl(results, record)
        done.add((question.id, model.name, digest))
        asked += 1
    return RunSummary(asked=asked, cached=cached)
