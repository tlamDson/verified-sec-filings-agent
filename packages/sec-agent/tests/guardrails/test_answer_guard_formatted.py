"""A recommendation behind a label or markdown ("**Recommendation:** Buy", "- Verdict: buy",
"Bottom line - buy", "Recommendation -- Overweight") is advice: the filter drops it.
Every text here is simulated.
"""

import pytest
from advice_cases import FORMATTED_RECOMMENDATIONS, UNFORMATTED_FACTS

from sec_agent.guardrails.advice import advice_rule
from sec_agent.guardrails.answer import guard_answer

FACTS = "Apple's revenue for fiscal 2024 was $391.0 billion."


@pytest.mark.parametrize("text", ["**Recommendation:** Buy", "- Verdict: buy", "Bottom line - buy"])
def test_the_three_reported_forms_are_dropped_from_an_answer(text: str) -> None:
    guard = guard_answer(
        f"{FACTS}\n\n{text}\n\nRevenue grew 2%.", canary=None, advice_requested=False
    )
    assert guard.advice_dropped == 1, text
    assert text not in guard.text, text
    assert FACTS in guard.text, text


def test_every_formatted_recommendation_is_advice() -> None:
    missed = [text for text in FORMATTED_RECOMMENDATIONS if advice_rule(text) is None]
    assert not missed, missed[:10]


def test_a_formatted_recommendation_is_dropped_from_a_full_answer() -> None:
    missed = [
        text
        for text in FORMATTED_RECOMMENDATIONS
        if guard_answer(
            f"{FACTS}\n\n{text}\n\nRevenue grew 2%.", canary=None, advice_requested=False
        ).advice_dropped
        != 1
    ]
    assert not missed, missed[:10]


@pytest.mark.parametrize("text", UNFORMATTED_FACTS)
def test_a_label_with_no_call_is_kept(text: str) -> None:
    assert advice_rule(text) is None, text
