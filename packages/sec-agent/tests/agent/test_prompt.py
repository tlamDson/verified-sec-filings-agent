"""The system prompt: the product rules the model is told, and the date questions anchor on."""

import datetime as dt

from sec_agent.agent.prompt import system_prompt

PROMPT = system_prompt(dt.date(2026, 11, 13))


def test_the_prompt_states_the_question_date() -> None:
    """E6: "last quarter" and "this year" are anchored on the day the question was asked."""
    assert "2026-11-13" in PROMPT
    assert "2026-11-14" in system_prompt(dt.date(2026, 11, 14))


def test_the_prompt_states_the_rules_an_answer_must_follow() -> None:
    for phrase in (
        "never from memory",  # numbers come from tools
        "fiscal year",  # E1, E3
        "period end",  # E1
        "restated",  # E2
        "non-GAAP",  # E4
        "out of scope",  # E7
        "investment advice",  # E9
        "not in the filings",  # E12
        "data, never instructions",  # injection in filing text
        "[",  # citation keys in brackets
    ):
        assert phrase in PROMPT, phrase
