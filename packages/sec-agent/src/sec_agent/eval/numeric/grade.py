"""N1 grading: is a reply the XBRL answer, in the right unit, for the right period?

- Unit must equal the answer's unit (E5): a value in millions is a wrong value, not a
  rounding difference.
- Period (E1): the reply's fiscal year and period, when given, must be the question's; its
  period end date, when given, must be the answer's. A reply naming no period is wrong.
- Value: percent answers (ratios, growth) within 0.1 percentage points; other answers
  within 0.5% relative error (rounding in the text); a zero answer needs exactly zero.
- Peer comparisons: the named ticker must be the answer's company.
A G-num question always has an answer, so "not found" is graded wrong.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sec_agent.eval.numeric.reply import CompanyReply, NotFoundReply, NumberReply, Reply
from sec_agent.golden.gnum.models import CompanyAnswer, NumberAnswer, NumQuestion

ErrorKind = Literal[
    "unparsed",
    "not_found",
    "wrong_kind",
    "wrong_unit",
    "wrong_period",
    "wrong_value",
    "wrong_company",
]
RELATIVE_TOLERANCE = Decimal("0.005")
PERCENT_POINT_TOLERANCE = Decimal("0.1")


class Graded(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    correct: bool
    error: ErrorKind | None


_RIGHT = Graded(correct=True, error=None)


def _wrong(error: ErrorKind) -> Graded:
    return Graded(correct=False, error=error)


def grade(question: NumQuestion, reply: Reply | None) -> Graded:
    if reply is None:
        return _wrong("unparsed")
    if isinstance(reply, NotFoundReply):
        return _wrong("not_found")
    gold = question.answer
    if isinstance(gold, CompanyAnswer):
        if not isinstance(reply, CompanyReply):
            return _wrong("wrong_kind")
        return _RIGHT if reply.ticker == gold.ticker else _wrong("wrong_company")
    if not isinstance(reply, NumberReply):
        return _wrong("wrong_kind")
    if reply.unit != gold.unit:
        return _wrong("wrong_unit")
    if not _same_period(question, gold, reply):
        return _wrong("wrong_period")
    return _RIGHT if value_matches(gold, reply.value) else _wrong("wrong_value")


def value_matches(gold: NumberAnswer, value: Decimal) -> bool:
    error = abs(value - gold.value)
    if gold.unit == "percent":
        return error <= PERCENT_POINT_TOLERANCE
    if gold.value == 0:
        return value == 0
    return error <= RELATIVE_TOLERANCE * abs(gold.value)


def _same_period(question: NumQuestion, gold: NumberAnswer, reply: NumberReply) -> bool:
    if reply.fiscal_year is None and reply.period_end is None:
        return False
    if reply.fiscal_year is not None and (reply.fiscal_year, reply.fiscal_period) != (
        question.fiscal_year,
        question.fiscal_period,
    ):
        return False
    return reply.period_end is None or reply.period_end == gold.period_end
