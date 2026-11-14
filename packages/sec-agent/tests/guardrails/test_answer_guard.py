"""The answer guard: a canary in the model's text blocks the answer (the prompt leaked or
an injected instruction was followed); advice sentences are dropped and the disclaimer
added (E9). Every answer text here is simulated: it stands in for what a model writes.
"""

from sec_agent.guardrails.answer import guard_answer
from sec_agent.guardrails.canary import canary_line, leaks, new_canary
from sec_agent.guardrails.notices import (
    ADVICE_DECLINED_TEXT,
    ADVICE_DISCLAIMER,
    CANARY_BLOCKED_TEXT,
)

CANARY = "cnry-0123456789abcdef"
FACTS = "Apple's revenue for fiscal 2024 was $391.0 billion (period end 2024-09-28)."


def test_a_clean_answer_passes_unchanged() -> None:
    guard = guard_answer(FACTS, canary=CANARY, advice_requested=False)
    assert (guard.verdict, guard.text, guard.reason, guard.advice_dropped) == (
        "pass",
        FACTS,
        None,
        0,
    )


def test_the_canary_blocks_the_answer_in_any_case_or_spacing() -> None:
    for leaked in (CANARY, CANARY.upper(), "c n r y - 0123 4567 89ab cdef", "cnry0123456789abcdef"):
        guard = guard_answer(f"{FACTS} {leaked}", canary=CANARY, advice_requested=False)
        assert (guard.verdict, guard.reason, guard.text) == (
            "blocked",
            "canary_leak",
            CANARY_BLOCKED_TEXT,
        ), leaked


def test_an_advice_sentence_is_dropped_and_the_disclaimer_added() -> None:
    draft = f"{FACTS} You should buy Apple stock now. I recommend holding NVDA."
    guard = guard_answer(draft, canary=CANARY, advice_requested=False)
    assert guard.verdict == "trimmed"
    assert guard.advice_dropped == 2
    assert guard.text.startswith(FACTS)
    assert "buy" not in guard.text.replace(ADVICE_DISCLAIMER, "")
    assert guard.text.endswith(ADVICE_DISCLAIMER)


def test_an_advice_question_gets_the_disclaimer_once() -> None:
    guard = guard_answer(FACTS, canary=CANARY, advice_requested=True)
    assert guard.text == f"{FACTS}\n\n{ADVICE_DISCLAIMER}"
    already = f"{FACTS} This is not investment advice."
    assert guard_answer(already, canary=CANARY, advice_requested=True).text == already


def test_an_answer_that_was_only_advice_becomes_the_declined_notice() -> None:
    guard = guard_answer(
        "NVDA is a strong buy with a price target of $200.", canary=CANARY, advice_requested=True
    )
    assert (guard.verdict, guard.text) == ("trimmed", ADVICE_DECLINED_TEXT)


def test_historical_statements_are_not_advice() -> None:
    text = "Apple bought back shares in fiscal 2024. NVIDIA's revenue rose 126% that year."
    assert guard_answer(text, canary=None, advice_requested=False).verdict == "pass"


def test_canaries_are_random_and_stated_in_the_prompt_line() -> None:
    a, b = new_canary(), new_canary()
    assert a != b
    assert a.startswith("cnry-")
    assert a in canary_line(a)
    assert leaks(a, f"x {a} y")
    assert not leaks(a, b)


ORDINARY_ADVICE = (
    "I'd recommend purchasing NVIDIA shares.",
    "I’d suggest buying AAPL.",  # noqa: RUF001
    "We'd advise selling the stock.",
    "Buy AAPL.",
    "Sell NVDA.",
    "Buy.",
    "Consider buying NVIDIA shares.",
    "Go ahead and buy the stock.",
    "Short Apple stock.",
)


def test_ordinary_recommendations_are_dropped() -> None:
    for advice in ORDINARY_ADVICE:
        guard = guard_answer(f"{FACTS} {advice}", canary=CANARY, advice_requested=True)
        assert (guard.verdict, guard.advice_dropped) == ("trimmed", 1), advice
        assert advice not in guard.text, advice
        assert guard.text.startswith(FACTS), advice


def test_historical_trade_words_are_not_advice() -> None:
    for text in (
        "Purchase obligations totaled $16.5 billion at year end.",
        "Purchases of marketable securities were $48.7 billion.",
        "Sell-through improved in fiscal 2024.",
        "Buyback spending was $94.9 billion.",
        "Short-term investments were $35.2 billion.",
        "Purchase of property and equipment was $9.4 billion.",
    ):
        assert guard_answer(text, canary=None, advice_requested=False).verdict == "pass", text


HOLD_ADVICE = (
    "Hold AAPL.",
    "Hold your NVIDIA shares.",
    "Hold on to your Apple stock.",
    "Hold for now.",
    "Keep holding NVDA.",
    "Continue holding the stock.",
    "You should keep holding the stock.",
    "Investors should continue holding NVIDIA.",
    "I'd hold AAPL.",
    "I’d hold the shares.",  # noqa: RUF001
    "I would hold onto the shares.",
    "If I were you, I'd hold.",
    "AAPL is a hold.",
    "Apple remains a hold at these levels.",
    "Don't sell your NVIDIA shares.",
    "Do not sell the stock.",
    "Stay invested in Apple.",
)


def test_hold_advice_is_dropped() -> None:
    for advice in HOLD_ADVICE:
        guard = guard_answer(f"{FACTS} {advice}", canary=CANARY, advice_requested=True)
        assert (guard.verdict, guard.advice_dropped) == ("trimmed", 1), advice
        assert advice not in guard.text, advice
        assert guard.text.startswith(FACTS), advice


def test_historical_hold_words_are_not_advice() -> None:
    for text in (
        "Apple holds $29.9 billion in cash and cash equivalents.",
        "Holders of record numbered 23,301.",
        "Held-to-maturity securities were $1.2 billion.",
        "Holding company expenses were $0.4 billion.",
        "Hold-back amounts were $2.0 million.",
        "The company does not hold derivatives for trading purposes.",
    ):
        assert guard_answer(text, canary=None, advice_requested=False).verdict == "pass", text
