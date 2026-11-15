"""run_safety: each G-red item through a fresh agent, one record appended per item.

A run that stops part way is resumed: items already in the output file are skipped. Each
item gets its own conversation, so no item sees another's history.
"""

import datetime as dt
from collections.abc import Callable, Sequence
from pathlib import Path

from sec_agent.agent.answer import Answer
from sec_agent.agent.service import Agent
from sec_agent.eval.safety.grade import grade
from sec_agent.eval.safety.records import SafetyRecord
from sec_agent.golden.gred.models import RedItem
from sec_agent.golden.jsonl import append_jsonl, read_jsonl

AgentFactory = Callable[[RedItem], Agent]


def run_safety(
    items: Sequence[RedItem],
    make_agent: AgentFactory,
    *,
    system: str,
    out: Path,
    asked_on: dt.date,
    progress: Callable[[SafetyRecord], None] | None = None,
) -> int:
    """Run the items not yet in `out`; return how many ran."""
    done = {r.item_id for r in read_jsonl(out, SafetyRecord)} if out.exists() else set[str]()
    ran = 0
    for item in items:
        if item.id in done:
            continue
        answer = make_agent(item).ask(f"{system}-{item.id}", item.question, asked_on=asked_on)
        record = safety_record(item, answer, system)
        append_jsonl(out, record)
        ran += 1
        if progress is not None:
            progress(record)
    return ran


def safety_record(item: RedItem, answer: Answer, system: str) -> SafetyRecord:
    graded = grade(item, answer)
    guard = answer.guardrails
    models = [c.model for c in answer.llm_calls if c.model]
    return SafetyRecord(
        item_id=item.id,
        kind=item.kind,
        system=system,
        status=answer.status,
        reason=answer.reason,
        text=answer.text,
        attack_succeeded=graded.attack_succeeded,
        exposed=graded.exposed,
        refused=graded.refused,
        llm_calls=len(answer.llm_calls),
        model=models[-1] if models else None,
        question_screen=None if guard is None else guard.question,
        flagged_passages=0 if guard is None else guard.flagged_passages,
        advice_dropped=0 if guard is None else guard.advice_dropped,
    )
