"""Run a numeric system over G-num questions: a cache of every answer, and a results file.

Two files per system. The cache (`SYSTEM.cache.jsonl`) gets every answer appended and
flushed as it arrives, so an interrupted night keeps what it finished; a rerun asks only
questions whose (question, model, prompt hash) has no cached answer, so changing the model
or the prompt (or the retrieved passages) asks again and the rest costs nothing. The
results file (`SYSTEM.jsonl`) is rewritten at the end of every run with exactly one answer
per question, for this run's model and prompts, whether cached or new: what is scored is
always what was asked for, never an answer left over from another model or prompt. The
raw output is stored; grading reads it later, so a grading fix never needs the model again.
"""

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.eval.numeric.baselines import ChatModel, Message, NumericSystem
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.jsonl import append_jsonl, read_jsonl, write_jsonl


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


def cache_path(results: Path) -> Path:
    """`results/b0.jsonl` -> `results/b0.cache.jsonl`."""
    return results.with_name(f"{results.stem}.cache.jsonl")


def run_numeric(
    questions: Sequence[NumQuestion],
    system: NumericSystem,
    model: ChatModel,
    *,
    results: Path,
    now: Callable[[], dt.datetime],
) -> RunSummary:
    cache = cache_path(results)
    existing = read_jsonl(cache, AnswerRecord)
    others = sorted({r.system for r in existing} - {system.name})
    if others:
        raise ValueError(f"{cache} holds answers of {others}, not of {system.name}")
    done = {(r.qid, r.model, r.prompt_sha256): r for r in existing}
    current: list[AnswerRecord] = []
    asked = cached = 0
    for question in questions:
        messages = system.prompt(question)
        key = (question.id, model.name, prompt_sha256(messages))
        record = done.get(key)
        if record is not None:
            cached += 1
        else:
            record = AnswerRecord(
                qid=question.id,
                system=system.name,
                model=model.name,
                prompt_sha256=key[2],
                output=model.complete(messages),
                answered_at=now(),
            )
            append_jsonl(cache, record)
            done[key] = record
            asked += 1
        current.append(record)
    write_jsonl(results, current)
    return RunSummary(asked=asked, cached=cached)
