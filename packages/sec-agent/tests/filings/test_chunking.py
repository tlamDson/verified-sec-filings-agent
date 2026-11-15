"""Section text to chunks of at most `max_tokens`, cut at paragraph, then sentence, then word."""

import pytest

from sec_agent.filings.chunking import chunk_spans
from sec_agent.filings.tokens import count_tokens


def _sentence(n: int, words: int = 9) -> str:
    return f"Sentence {n} " + " ".join(["word"] * (words - 3)) + " ends."


def _paragraph(start: int, sentences: int) -> str:
    return " ".join(_sentence(start + i) for i in range(sentences))


def _assert_covers(text: str, spans: list[tuple[int, int]]) -> None:
    """Spans are in order, do not overlap, and leave out only whitespace."""
    cursor = 0
    for start, end in spans:
        assert start >= cursor
        assert text[cursor:start].strip() == ""
        assert text[start:end] == text[start:end].strip()
        cursor = end
    assert text[cursor:].strip() == ""


def test_count_tokens_counts_words_and_punctuation() -> None:
    assert count_tokens("") == 0
    assert count_tokens("Net sales rose 12% to $1,234.") == 11
    assert count_tokens("Company\u2019s") == 3


def test_empty_or_blank_text_has_no_chunks() -> None:
    assert chunk_spans("", 50) == []
    assert chunk_spans(" \n \n", 50) == []


def test_short_paragraphs_pack_into_one_chunk() -> None:
    text = "First paragraph.\nSecond paragraph."
    assert chunk_spans(text, 50) == [(0, len(text))]


def test_chunks_break_at_paragraph_boundaries_when_the_next_paragraph_does_not_fit() -> None:
    paragraphs = [_paragraph(0, 3), _paragraph(10, 3), _paragraph(20, 3)]  # 30 tokens each
    text = "\n".join(paragraphs)
    spans = chunk_spans(text, 70)
    assert [text[s:e] for s, e in spans] == ["\n".join(paragraphs[:2]), paragraphs[2]]


def test_long_paragraph_splits_at_sentences() -> None:
    text = _paragraph(0, 10)  # ten sentences of 10 tokens
    spans = chunk_spans(text, 35)
    _assert_covers(text, spans)
    pieces = [text[s:e] for s, e in spans]
    assert all(count_tokens(p) <= 35 for p in pieces)
    assert all(p.endswith("ends.") for p in pieces)
    assert len(pieces) == 4


def test_overlong_sentence_splits_at_word_boundaries() -> None:
    text = " ".join(f"w{i}" for i in range(120))
    spans = chunk_spans(text, 50)
    _assert_covers(text, spans)
    assert [count_tokens(text[s:e]) for s, e in spans] == [50, 50, 20]


@pytest.mark.parametrize("max_tokens", [20, 50, 400])
def test_every_chunk_fits_and_together_they_cover_the_text(max_tokens: int) -> None:
    text = "\n".join([_paragraph(0, 2), "Heading", _paragraph(5, 30), "x " * 90, _paragraph(50, 1)])
    spans = chunk_spans(text, max_tokens)
    _assert_covers(text, spans)
    assert all(0 < count_tokens(text[s:e]) <= max_tokens for s, e in spans)
    assert chunk_spans(text, max_tokens) == spans  # deterministic


def test_max_tokens_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        chunk_spans("text", 0)
