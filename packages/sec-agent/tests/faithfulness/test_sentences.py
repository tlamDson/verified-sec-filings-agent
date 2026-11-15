"""Cutting an answer into the sentences the checker keeps or drops. Simulated answer text."""

import itertools

import pytest

from sec_agent.faithfulness.sentences import split_sentences


def _texts(text: str) -> list[str]:
    return [text[s.start : s.end].strip() for s in split_sentences(text)]


def test_sentences_end_at_a_stop_followed_by_a_capital() -> None:
    text = "Revenue was $391.0 billion. Gross margin was 46.2%! Was it up? Yes [x]."
    assert _texts(text) == [
        "Revenue was $391.0 billion.",
        "Gross margin was 46.2%!",
        "Was it up?",
        "Yes [x].",
    ]


def test_a_decimal_point_or_an_abbreviation_before_lower_case_does_not_end_a_sentence() -> None:
    assert _texts("Apple Inc. reported $6.08 per share. NVIDIA did too.") == [
        "Apple Inc. reported $6.08 per share.",
        "NVIDIA did too.",
    ]


def test_every_line_is_its_own_sentence() -> None:
    text = "Figures:\n| AAPL | $391.0B |\n| NVDA | $60.9B |\n\n- one\n- two"
    assert _texts(text) == ["Figures:", "| AAPL | $391.0B |", "| NVDA | $60.9B |", "- one", "- two"]


@pytest.mark.parametrize(
    "text", ["", "One.", "One. Two.\n\nThree\n", "  lead and trail  ", "a.b. C\r\nD"]
)
def test_the_sentences_cover_the_whole_text_in_order(text: str) -> None:
    spans = split_sentences(text)
    assert "".join(text[s.start : s.end] for s in spans) == text
    assert all(a.end == b.start for a, b in itertools.pairwise(spans))
