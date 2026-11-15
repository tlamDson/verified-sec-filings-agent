"""Section text to chunk spans of at most `max_tokens` tokens.

The text is cut into pieces at line (paragraph) boundaries; a paragraph longer than the
limit is cut at sentence ends, and a sentence longer than the limit at token boundaries.
Pieces are then packed greedily, in order, into chunks. A chunk is a `(start, end)` span of
the section text, so its text is an exact, citable slice; only whitespace falls between
chunks. Chunks do not overlap.
"""

import re
from collections.abc import Iterator

from sec_agent.filings.tokens import count_tokens, token_spans

Span = tuple[int, int]

_LINE = re.compile(r"[^\n]+")
# A sentence ends at . ! or ? (and any closing quotes or brackets) before a space.
_SENTENCE = re.compile(r"\S.*?(?:[.!?][\"'\u201d\u2019)\]]*(?=\s)|$)")


def chunk_spans(text: str, max_tokens: int) -> list[Span]:
    if max_tokens < 1:
        raise ValueError(f"max_tokens must be positive, got {max_tokens}")
    chunks: list[Span] = []
    tokens_in_last = 0
    for span in _pieces(text, max_tokens):
        tokens = count_tokens(text[span[0] : span[1]])
        if chunks and tokens_in_last + tokens <= max_tokens:
            chunks[-1] = (chunks[-1][0], span[1])
            tokens_in_last += tokens
        else:
            chunks.append(span)
            tokens_in_last = tokens
    return chunks


def _pieces(text: str, max_tokens: int) -> Iterator[Span]:
    """Spans with at least one and at most `max_tokens` tokens, in text order."""
    for line in _LINE.finditer(text):
        n = count_tokens(line[0])
        if n == 0:
            continue
        if n <= max_tokens:
            yield _strip(text, line.span())
            continue
        for sentence in _SENTENCE.finditer(text, line.start(), line.end()):
            span = _strip(text, sentence.span())
            n = count_tokens(text[span[0] : span[1]])
            if 0 < n <= max_tokens:
                yield span
            elif n:
                yield from _windows(text, span, max_tokens)


def _windows(text: str, span: Span, max_tokens: int) -> Iterator[Span]:
    """Cut a span every `max_tokens` tokens, at token ends."""
    tokens = [(span[0] + a, span[0] + b) for a, b in token_spans(text[span[0] : span[1]])]
    for i in range(0, len(tokens), max_tokens):
        yield tokens[i][0], tokens[min(i + max_tokens, len(tokens)) - 1][1]


def _strip(text: str, span: Span) -> Span:
    start, end = span
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
