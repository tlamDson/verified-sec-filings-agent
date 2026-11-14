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


ADVICE_AFTER_THE_OBJECT = (
    "I can't give a price target you should buy NVDA.",
    "I can't give advice NVDA is a buy.",
    "I can't give a price target that NVDA will outperform the market.",
    "I can't give advice that you should buy NVDA.",
    "I can't give a rating NVDA looks undervalued.",
    "I can't give advice on NVDA you should buy it.",
    "I can't give a price target, or advice that you should buy NVDA.",
)
OBJECTS_THAT_STAY_DECLINES = (
    "I can't give a recommendation to buy NVDA now.",
    "I can't give recommendations to buy AAPL now.",
    "I can't give advice on whether to buy, sell or hold NVDA.",
    "I can't give a price target for NVDA.",
)


@pytest.mark.parametrize("sentence", ADVICE_AFTER_THE_OBJECT)
def test_advice_trailing_the_declined_object_is_read(sentence: str) -> None:
    assert advice_rule(sentence) is not None, sentence
    guard = guard_answer(
        f"{sentence} Revenue was $391.0 billion.", canary=None, advice_requested=True
    )
    assert guard.advice_dropped == 1, sentence
    assert "Revenue was $391.0 billion." in guard.text, sentence


@pytest.mark.parametrize("sentence", OBJECTS_THAT_STAY_DECLINES)
def test_an_object_with_its_own_complement_is_still_a_decline(sentence: str) -> None:
    assert advice_rule(sentence) is None, sentence


DATED_DECLINES = (
    "I can't give a price target for 2025",
    "I can't give a 12-month price target",
    "I can't give a price target for fiscal 2026 or Q3",
    "I can't give a forecast for December 31, 2025",
    "I can't give advice on NVDA for FY2025",
)


@pytest.mark.parametrize("decline", DATED_DECLINES)
def test_a_dated_decline_keeps_the_alternative(decline: str) -> None:
    assert advice_rule(f"{decline}.") is None, decline
    text = f"{decline}, but {ALTERNATIVE}."
    guard = guard_answer(text, canary=None, advice_requested=True)
    assert guard.advice_dropped == 0, text
    assert ALTERNATIVE in guard.text, text


TRAILING_ORDERS = (
    "I can't give advice on NVDA buy it now.",
    "I can't give advice on NVDA just buy it.",
    "I can't give a recommendation about AAPL so buy AAPL today.",
    "I can't give advice for this stock sell it.",
    "I can't give a price target for 2025 you should buy NVDA.",
    "I can't give a price target for 2025, my price target is $300.",
)


@pytest.mark.parametrize("sentence", TRAILING_ORDERS)
def test_an_order_trailing_a_complement_is_read(sentence: str) -> None:
    assert advice_rule(sentence) is not None, sentence


CURRENCY_TARGETS = (
    "I can't give a price target of $2025.",
    "I can't give a price target around $2030.",
    "I can't give a price target of €2025.",
    "I can't give a price target near 2025 dollars.",
    "I can't give a price target to 2030.",
    "I can't give a 2025 USD price target.",
)


@pytest.mark.parametrize("sentence", CURRENCY_TARGETS)
def test_a_currency_target_is_not_a_date(sentence: str) -> None:
    assert advice_rule(sentence) is not None, sentence


COORDINATED_DECLINES = (
    "I can neither recommend a stock nor give a price target",
    "I can neither recommend nor rate NVDA",
    "I will neither recommend buying nor predict the price",
    "I can't recommend a stock nor give a price target for 2025",
)


@pytest.mark.parametrize("decline", COORDINATED_DECLINES)
def test_a_coordinated_decline_keeps_the_alternative(decline: str) -> None:
    assert advice_rule(f"{decline}.") is None, decline
    text = f"{decline}, but {ALTERNATIVE}."
    guard = guard_answer(text, canary=None, advice_requested=True)
    assert guard.advice_dropped == 0, text
    assert ALTERNATIVE in guard.text, text


def test_advice_after_a_coordinated_decline_is_read() -> None:
    assert advice_rule("I can neither recommend a stock nor predict it, but buy NVDA now.")
    assert advice_rule("I can neither recommend a stock nor give advice you should buy NVDA.")
