"""Seeded order without a random generator: rank items by a SHA-256 of seed and key.

The hash depends only on the seed and the item's own key, so adding or removing one item
never reorders the others, and the order is the same on every machine and Python version.
"""

import hashlib
import json
from collections.abc import Iterable, Sequence


def seeded_key(seed: int, *parts: object) -> str:
    """Hex SHA-256 of the compact JSON array [seed, *parts as strings]."""
    payload = json.dumps([seed, *(str(p) for p in parts)], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def round_robin[T](groups: Iterable[Sequence[T]]) -> list[T]:
    """One item from each group in turn, until every group is used up."""
    pending = [list(g) for g in groups]
    out: list[T] = []
    depth = 0
    while any(depth < len(g) for g in pending):
        out.extend(g[depth] for g in pending if depth < len(g))
        depth += 1
    return out
