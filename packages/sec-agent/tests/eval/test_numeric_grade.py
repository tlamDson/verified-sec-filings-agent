"""N1: reading a system's reply and grading it against the XBRL answer."""

import datetime as dt
from decimal import Decimal

import pytest
from eval_data import FY_END, number_question, peer_question

from sec_agent.eval.numeric.grade import grade
from sec_agent.eval.numeric.reply import CompanyReply, NotFoundReply, NumberReply, parse_reply

REVENUE = number_question("revenue", "60922000000")
MARGIN = number_question("gross_margin", "72.718", unit="percent", qtype="ratio")
PEER = peer_question("revenue")


def _number(value: str, unit: str = "USD", **period: object) -> NumberReply:
    fields: dict[str, object] = {"fiscal_year": 2024, "fiscal_period": "FY"}
    fields.update(period)
    return NumberReply.model_validate({"answer": "number", "value": value, "unit": unit, **fields})


def test_parse_reply_takes_the_last_json_object_with_an_answer() -> None:
    text = (
        'Thinking about {"draft": 1}. Revenue was $60.9 billion.\n'
        '```json\n{"answer": "number", "value": 60922000000, "unit": "USD",'
        ' "fiscal_year": 2024, "fiscal_period": "FY", "period_end": "2024-01-28",'
        ' "citation": "x"}\n```'
    )
    reply = parse_reply(text)
    assert reply == NumberReply(
        answer="number",
        value=Decimal(60922000000),
        unit="USD",
        fiscal_year=2024,
        fiscal_period="FY",
        period_end=dt.date(2024, 1, 28),
    )


def test_parse_reply_keeps_decimal_precision_and_strips_separators() -> None:
    reply = parse_reply('{"answer": "number", "value": "$1,234.5678901234", "unit": "USD"}')
    assert isinstance(reply, NumberReply)
    assert reply.value == Decimal("1234.5678901234")
    reply = parse_reply('{"answer": "number", "value": 0.1000000000000000055, "unit": "percent"}')
    assert isinstance(reply, NumberReply)
    assert reply.value == Decimal("0.1000000000000000055")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"answer": "company", "ticker": "simb"}', CompanyReply(answer="company", ticker="SIMB")),
        ('{"answer": "not_found"}', NotFoundReply(answer="not_found")),
    ],
)
def test_parse_other_replies(text: str, expected: object) -> None:
    assert parse_reply(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Revenue was 60.9 billion.",
        '{"answer": "number", "value": "about 61 billion", "unit": "USD"}',
        '{"answer": "number", "value": 1, "unit": "USD millions"}',
        '{"answer": "maybe"}',
        '{"answer": "number", "value": 1, "unit": "USD", "fiscal_year": 2024}',
    ],
)
def test_unparseable_replies_are_none(text: str) -> None:
    assert parse_reply(text) is None


def test_value_within_half_a_percent_is_correct() -> None:
    assert grade(REVENUE, _number("61200000000")).correct  # +0.46%
    result = grade(REVENUE, _number("61300000000"))  # +0.62%
    assert (result.correct, result.error) == (False, "wrong_value")


def test_value_in_millions_is_a_wrong_value_e5() -> None:
    assert grade(REVENUE, _number("60922")).error == "wrong_value"


def test_percent_answers_allow_a_tenth_of_a_point() -> None:
    assert grade(MARGIN, _number("72.8", "percent")).correct
    assert grade(MARGIN, _number("72.83", "percent")).error == "wrong_value"


def test_unit_must_match() -> None:
    assert grade(REVENUE, _number("60922000000", "shares")).error == "wrong_unit"


def test_fiscal_labels_must_match_e1() -> None:
    assert grade(REVENUE, _number("60922000000", fiscal_year=2023)).error == "wrong_period"
    assert grade(REVENUE, _number("60922000000", fiscal_period="Q4")).error == "wrong_period"


def test_period_end_when_given_must_match() -> None:
    assert grade(REVENUE, _number("60922000000", period_end=FY_END)).correct
    late = _number("60922000000", period_end=dt.date(2024, 12, 31))
    assert grade(REVENUE, late).error == "wrong_period"


def test_period_end_alone_is_enough() -> None:
    reply = _number("60922000000", fiscal_year=None, fiscal_period=None, period_end=FY_END)
    assert grade(REVENUE, reply).correct


def test_a_reply_without_any_period_is_wrong() -> None:
    reply = _number("60922000000", fiscal_year=None, fiscal_period=None)
    assert grade(REVENUE, reply).error == "wrong_period"


def test_zero_answer_needs_zero() -> None:
    zero = number_question("dividends", "0")
    assert grade(zero, _number("0")).correct
    assert grade(zero, _number("0.01")).error == "wrong_value"


def test_peer_comparison_needs_the_right_ticker() -> None:
    assert grade(PEER, CompanyReply(answer="company", ticker="SIMB")).correct
    assert grade(PEER, CompanyReply(answer="company", ticker="SIMW")).error == "wrong_company"
    assert grade(PEER, _number("1")).error == "wrong_kind"
    assert grade(REVENUE, CompanyReply(answer="company", ticker="SIMB")).error == "wrong_kind"


def test_not_found_and_unparsed_are_wrong() -> None:
    assert grade(REVENUE, NotFoundReply(answer="not_found")).error == "not_found"
    assert grade(REVENUE, None).error == "unparsed"
