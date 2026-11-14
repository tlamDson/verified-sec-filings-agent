"""N1 probes: trap replies built by code from the G-num answers, each with the grade the N1
grader must give it. They are not model output and are never reported as an accuracy; the
gate only checks that the grader still sorts every trap the same way.

The recorded answers do not exercise every rule (no reply in them has the right year but
the wrong fiscal period, for example), so a grader bug there would pass the recorded scores
unchanged. Each probe case aims at one rule: E1 period, E5 unit, the value tolerance, the
last JSON reply, and the peer ticker (E3).
"""

import json
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.numeric.grade import grade
from sec_agent.eval.numeric.reply import parse_reply
from sec_agent.golden.gnum.models import CompanyAnswer, NumQuestion

PER_TYPE = 5
"""Questions per question type, the first by id."""


class Probe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    qid: str
    case: str
    output: str
    expect: str
    """`correct` or the N1 error kind."""


def build_probes(questions: Sequence[NumQuestion]) -> list[Probe]:
    by_type: defaultdict[str, list[NumQuestion]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q.id):
        if len(by_type[q.qtype]) < PER_TYPE:
            by_type[q.qtype].append(q)
    return [p for qs in by_type.values() for q in qs for p in _probes(q)]


def probe_scores(
    questions: Sequence[NumQuestion], probes: Sequence[Probe]
) -> dict[str, tuple[float, int]]:
    """Case -> (share of its probes graded as expected, how many probes)."""
    by_id = {q.id: q for q in questions}
    hits: defaultdict[str, list[bool]] = defaultdict(list)
    for p in probes:
        graded = grade(by_id[p.qid], parse_reply(p.output))
        hits[p.case].append((graded.error or "correct") == p.expect)
    return {case: (sum(h) / len(h), len(h)) for case, h in sorted(hits.items())}


def _line(**reply: object) -> str:
    return json.dumps(reply, default=str)


def _probes(q: NumQuestion) -> list[Probe]:
    gold = q.answer
    if isinstance(gold, CompanyAnswer):
        other = "ZZZZ" if gold.ticker != "ZZZZ" else "YYYY"
        return [
            Probe(
                qid=q.id,
                case="right_peer",
                output=_line(answer="company", ticker=gold.ticker),
                expect="correct",
            ),
            Probe(
                qid=q.id,
                case="wrong_peer",
                output=_line(answer="company", ticker=other),
                expect="wrong_company",
            ),
        ]
    period = {"fiscal_year": q.fiscal_year, "fiscal_period": q.fiscal_period}
    value = gold.value
    near = value + (Decimal("0.05") if gold.unit == "percent" else value * Decimal("0.004"))
    far = value + (Decimal("1") if gold.unit == "percent" else value * Decimal("0.02"))
    if value == 0:
        far = Decimal("1")
    other_period = "Q1" if q.fiscal_period == "FY" else "FY"
    other_unit = "shares" if gold.unit != "shares" else "USD"
    right = _line(answer="number", value=value, unit=gold.unit, **period)
    cases = {
        "exact": (right, "correct"),
        "rounded": (_line(answer="number", value=near, unit=gold.unit, **period), "correct"),
        "off_value": (_line(answer="number", value=far, unit=gold.unit, **period), "wrong_value"),
        "other_period": (
            _line(
                answer="number",
                value=value,
                unit=gold.unit,
                fiscal_year=q.fiscal_year,
                fiscal_period=other_period,
            ),
            "wrong_period",
        ),
        "other_unit": (
            _line(answer="number", value=value, unit=other_unit, **period),
            "wrong_unit",
        ),
        "no_period": (_line(answer="number", value=value, unit=gold.unit), "wrong_period"),
        "draft_then_final": (
            f"Draft: {_line(answer='number', value=far, unit=gold.unit, **period)}\nFinal: {right}",
            "correct",
        ),
    }
    return [Probe(qid=q.id, case=c, output=o, expect=e) for c, (o, e) in cases.items()]
