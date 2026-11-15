"""split_sentences: an answer cut into the pieces the checker keeps or drops whole.

Every line is a piece of its own (a list item, a table row), and a line is cut after ".",
"!" or "?" followed by a space and a capital, a digit, "$" or a bracket, so neither a
decimal point nor "Inc. reported" ends a sentence. The pieces cover the text exactly:
each holds its sentence and the whitespace after it.
"""

import re
from dataclasses import dataclass

_BREAK = re.compile(r"[.!?][\"')\]]*[ \t]+(?=[A-Z0-9\[(\"*_$])")


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int


def split_sentences(text: str) -> tuple[Sentence, ...]:
    pieces: list[tuple[int, int]] = []
    start = 0
    for line in text.splitlines(keepends=True):
        cut = start
        for match in _BREAK.finditer(line):
            pieces.append((cut, start + match.end()))
            cut = start + match.end()
        pieces.append((cut, start + len(line)))
        start += len(line)
    return tuple(Sentence(a, b) for a, b in _merge_blank(text, pieces))


def _merge_blank(text: str, pieces: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """A piece of whitespace only joins the piece before it (or after it, at the start)."""
    merged: list[tuple[int, int]] = []
    pending: int | None = None
    for a, b in pieces:
        if not text[a:b].strip():
            if merged:
                merged[-1] = (merged[-1][0], b)
            elif pending is None:
                pending = a
            continue
        merged.append((a if pending is None else pending, b))
        pending = None
    if pending is not None:
        merged.append((pending, len(text)))
    return merged
