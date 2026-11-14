"""The advice filter keeps what follows a decline: "I can't recommend a stock or give a
price target, but here is the reported revenue" loses nothing. The decline's own object
("a price target") is not advice, and advice joined after it is still dropped. Every text
here is simulated: it stands in for what a model writes.
"""

import pytest

from sec_agent.guardrails.advice import advice_rule
from sec_agent.guardrails.answer import guard_answer

ALTERNATIVE = "here is the reported revenue: $391.0 billion for fiscal 2024"
DECLINES_WITH_AN_ARTICLE = (
    "I can't give a price target",
    "I can't give you a price target",
    "I can't recommend a stock or give a price target",
    "I can't recommend a stock, or give price targets",
    "I can't recommend a stock, give a price target, or predict where it goes",
    "I can't provide a price target or a buy rating",
    "I can't recommend a stock and I can't give a price target",
    "I cannot provide your price target",
)


@pytest.mark.parametrize("decline", DECLINES_WITH_AN_ARTICLE)
def test_an_alternative_after_a_decline_is_kept(decline: str) -> None:
    text = f"{decline}, but {ALTERNATIVE}."
    guard = guard_answer(text, canary=None, advice_requested=True)
    assert guard.advice_dropped == 0, text
    assert ALTERNATIVE in guard.text, text


@pytest.mark.parametrize("decline", DECLINES_WITH_AN_ARTICLE)
def test_a_decline_alone_is_kept(decline: str) -> None:
    assert advice_rule(f"{decline}.") is None, decline


@pytest.mark.parametrize("decline", DECLINES_WITH_AN_ARTICLE)
def test_advice_after_the_decline_is_still_dropped(decline: str) -> None:
    text = f"{decline}, but you should buy NVDA. Revenue was $391.0 billion."
    guard = guard_answer(text, canary=None, advice_requested=True)
    assert guard.advice_dropped == 1, text
    assert "buy NVDA" not in guard.text, text
    assert "Revenue was $391.0 billion." in guard.text, text


def test_a_price_target_with_a_number_is_still_dropped() -> None:
    assert advice_rule("I can't give advice, but my price target is $300.") == "price_target"
    assert advice_rule("I can't recommend a stock or say more than a price target of $300.")
