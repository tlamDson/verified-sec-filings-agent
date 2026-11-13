"""Paragraph diff of two risk factor sections, deterministic and order-independent.

A section's text holds one block per line (`sec_agent.filings.sections`). Blocks without a
letter (page numbers) are dropped. Then:

1. Blocks equal after case folding and collapsing whitespace are unchanged, wherever they
   moved; duplicates pair one to one.
2. Of the rest, old and new blocks pair as `changed` greedily, most similar first, while
   their similarity (Jaccard index of their word sets) is at least `CHANGED_THRESHOLD`;
   ties break by position.
3. New blocks left over are `added`, old ones `removed`.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from typing import NamedTuple

CHANGED_THRESHOLD = 0.5
_LINE = re.compile(r"[^\n]+")
_LETTER = re.compile(r"[^\W\d_]")
_WORD = re.compile(r"[^\W_]+")


class Block(NamedTuple):
    text: str
    start: int
    """Offset in the section text: `section[start:end] == text`."""
    end: int


class ChangedPair(NamedTuple):
    old: Block
    new: Block
    similarity: float


class BlockDiff(NamedTuple):
    added: tuple[Block, ...]
    removed: tuple[Block, ...]
    changed: tuple[ChangedPair, ...]
    unchanged: int


def split_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    for m in _LINE.finditer(text):
        line = m.group()
        stripped = line.strip()
        if not _LETTER.search(stripped):
            continue
        start = m.start() + (len(line) - len(line.lstrip()))
        blocks.append(Block(stripped, start, start + len(stripped)))
    return blocks


def _normal(text: str) -> str:
    return " ".join(text.casefold().split())


def _words(text: str) -> frozenset[str]:
    return frozenset(_WORD.findall(text.casefold()))


def similarity(a: str, b: str) -> float:
    """Jaccard index of the two texts' word sets; two empty texts are equal."""
    return _jaccard(_words(a), _words(b))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def diff_blocks(old: Sequence[Block], new: Sequence[Block]) -> BlockDiff:
    pending: defaultdict[str, list[int]] = defaultdict(list)
    for i, block in enumerate(old):
        pending[_normal(block.text)].append(i)
    matched_old: set[int] = set()
    rest_new: list[int] = []
    for j, block in enumerate(new):
        queue = pending.get(_normal(block.text))
        if queue:
            matched_old.add(queue.pop(0))
        else:
            rest_new.append(j)
    rest_old = [i for i in range(len(old)) if i not in matched_old]
    words_old = {i: _words(old[i].text) for i in rest_old}
    words_new = {j: _words(new[j].text) for j in rest_new}
    candidates: list[tuple[float, int, int]] = []
    for i in rest_old:
        for j in rest_new:
            score = _jaccard(words_old[i], words_new[j])
            if score >= CHANGED_THRESHOLD:
                candidates.append((score, i, j))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_old: set[int] = set()
    used_new: set[int] = set()
    pairs: list[ChangedPair] = []
    for score, i, j in candidates:
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        pairs.append(ChangedPair(old[i], new[j], score))
    pairs.sort(key=lambda p: p.new.start)
    return BlockDiff(
        added=tuple(new[j] for j in rest_new if j not in used_new),
        removed=tuple(old[i] for i in rest_old if i not in used_old),
        changed=tuple(pairs),
        unchanged=len(matched_old),
    )
