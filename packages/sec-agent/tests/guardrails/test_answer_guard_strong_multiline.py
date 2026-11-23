"""T-0008: a strong call with markdown inside it ("**Recommendation:** **Strong** Buy") and a
label whose call is on the next line ("**Recommendation:**\nOverweight") are advice: the
filter drops them and keeps the facts around them. Every text here is simulated.
"""

import pytest
from advice_cases import FORMATTED_STRONG_RECOMMENDATIONS, MULTILINE_RECOMMENDATIONS

from sec_agent.guardrails.advice import advice_rule
from sec_agent.guardrails.answer import guard_answer
from sec_agent.guardrails.notices import ADVICE_DISCLAIMER

FACTS = "Apple's revenue for fiscal 2024 was $391.0 billion."
AFTER = "Revenue grew 2%."


def _leaks(text: str) -> bool:
    """The full answer still shows a call, or lost the facts around it."""
    guard = guard_answer(f"{FACTS}\n\n{text}\n\n{AFTER}", canary=None, advice_requested=False)
    shown = guard.text.replace(ADVICE_DISCLAIMER, "")
    return (
        guard.advice_dropped < 1
        or advice_rule(shown) is not None
        or FACTS not in shown
        or AFTER not in shown
    )


@pytest.mark.parametrize(
    "text", ["**Recommendation:** **Strong** Buy", "**Recommendation:** Strong **Buy**"]
)
def test_the_reported_strong_calls_are_advice(text: str) -> None:
    assert advice_rule(text) is not None, text
    assert not _leaks(text), text


@pytest.mark.parametrize("text", ["**Recommendation:**\n_Buy_", "**Recommendation:**\nOverweight"])
def test_the_reported_multiline_calls_are_dropped_from_an_answer(text: str) -> None:
    assert not _leaks(text), text


def test_every_formatted_strong_call_is_advice() -> None:
    missed = [text for text in FORMATTED_STRONG_RECOMMENDATIONS if advice_rule(text) is None]
    assert not missed, missed[:10]


def test_every_formatted_strong_call_is_dropped_from_a_full_answer() -> None:
    missed = [text for text in FORMATTED_STRONG_RECOMMENDATIONS if _leaks(text)]
    assert not missed, missed[:10]


def test_every_multiline_call_is_dropped_from_a_full_answer() -> None:
    missed = [text for text in MULTILINE_RECOMMENDATIONS if _leaks(text)]
    assert not missed, missed[:10]


@pytest.mark.parametrize(
    "text",
    [
        "Verdict:\nthe court held that the claim failed.",
        "**Recommendation:**\nsee the risk factors in Item 1A.",
        "Rating -\noutlook stable.",
        "Strong\nbuyback activity continued in fiscal 2024.",
    ],
)
def test_a_label_with_no_call_on_the_next_line_is_kept(text: str) -> None:
    guard = guard_answer(f"{FACTS}\n\n{text}", canary=None, advice_requested=False)
    assert guard.advice_dropped == 0, text
    assert guard.text == f"{FACTS}\n\n{text}", text
