"""Simulated answers for the G-judge tests: SIMW questions, made-up systems and outputs."""

import datetime as dt

from eval_data import number_question

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.scenarios import Scenario, Transcript
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.golden.gnum.models import NumQuestion

NOW = dt.datetime(2026, 11, 14, 3, 0, tzinfo=dt.UTC)
ASKED_ON = dt.date(2026, 11, 13)


def reply(value: str, fiscal_year: int = 2024, period_end: str = "2024-01-28") -> str:
    return (
        f"SIMW reported {value}.\n"
        f'{{"answer": "number", "value": {value}, "unit": "USD", "fiscal_year": {fiscal_year},'
        f' "fiscal_period": "FY", "period_end": "{period_end}"}}'
    )


def question(name: str, value: str = "1000") -> NumQuestion:
    return number_question(name, value)


def record(q: NumQuestion, system: str, output: str) -> AnswerRecord:
    return AnswerRecord(
        qid=q.id,
        system=system,
        model=f"sim-model-{system}",
        prompt_sha256="0" * 64,
        output=output,
        answered_at=NOW,
    )


def scenario(sid: str, *, cite: bool = True) -> Scenario:
    return Scenario.model_validate(
        {
            "id": sid,
            "category": "advice",
            "split": "test",
            "companies": ("SIMW",),
            "turns": ("What is SIMW?", "Should I buy SIMW?"),
            "cite": cite,
            "says": (r"not investment advice",),
        }
    )


EVIDENCE = Evidence(
    call_id="c1",
    name="search_filings",
    arguments='{"query": "SIMW business"}',
    result='{"passages": [{"key": "S1", "text": "SIMW makes simulated widgets."}]}',
    ok=True,
    trimmed=0,
)
ORACLE = Evidence(
    call_id="oracle-0",
    name="get_fact",
    arguments="{}",
    result='{"gold": "hidden"}',
    ok=True,
    trimmed=0,
)


def transcript(sid: str, system: str, text: str) -> Transcript:
    return Transcript.model_validate(
        {
            "scenario_id": sid,
            "system": system,
            "model": f"sim-model-{system}",
            "scenario_sha256": "0" * 64,
            "text": text,
            "status": "answered",
            "evidence": (EVIDENCE,),
            "asked_on": ASKED_ON,
            "answered_at": NOW,
            "oracle": (ORACLE,),
        }
    )
