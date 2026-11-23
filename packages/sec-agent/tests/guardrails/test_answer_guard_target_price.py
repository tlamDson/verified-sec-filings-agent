"""T-0007: after a "target price" or "exact price target" decline, only the declined
object goes; the reported figures after it stay. Every text here is simulated: it stands
in for what a model writes (the ticket's own wording).
"""

import pytest

from sec_agent.guardrails.advice import advice_rule
from sec_agent.guardrails.answer import guard_answer

FIGURES = "reported revenue was $391.0 billion for fiscal 2024"
DECLINES = (
    "I can't give a target price",
    "I can't give an exact price target",
    "I can't give an exact target price",
    "I cannot provide a precise price target",
    "I can't recommend a stock or give a target price",
)


@pytest.mark.parametrize("decline", DECLINES)
def test_the_figures_after_the_decline_are_kept(decline: str) -> None:
    text = f"{decline}, but {FIGURES}."
    guard = guard_answer(text, canary=None, advice_requested=True)
    assert guard.advice_dropped == 0, text
    assert guard.text.startswith(text), text


@pytest.mark.parametrize("decline", DECLINES)
def test_the_decline_alone_is_not_advice(decline: str) -> None:
    assert advice_rule(f"{decline}.") is None, decline


@pytest.mark.parametrize("decline", DECLINES)
def test_advice_after_the_decline_is_still_dropped(decline: str) -> None:
    text = f"{decline}, but you should buy NVDA. Revenue was $391.0 billion."
    guard = guard_answer(text, canary=None, advice_requested=True)
    assert guard.advice_dropped == 1, text
    assert "buy NVDA" not in guard.text, text
    assert "Revenue was $391.0 billion." in guard.text, text


@pytest.mark.parametrize(
    "sentence",
    [
        "I can't give advice, but my target price is $300.",
        "I can't give an exact price target of $300.",
        "I can't give a target price, but my exact price target is $300.",
    ],
)
def test_a_target_price_with_a_number_is_still_dropped(sentence: str) -> None:
    assert advice_rule(sentence) == "price_target", sentence
