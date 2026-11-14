"""Stratified, seeded G-judge sample: equal strata, spread over the answering systems.

Each stratum gets an equal share of `total`; a stratum with fewer answers gives all it
has and its unused share goes to the others, equally, earlier strata (in `STRATA` order)
taking any remainder. Within a stratum the answers are ranked by a seeded hash and taken
round-robin over the systems, so every system is in every stratum it can be. Item ids
are seeded hashes too, and the items are written in id order, which hides the stratum.
"""

import hashlib
from collections.abc import Mapping, Sequence

from sec_agent.eval.judge.models import (
    STRATA,
    BlindItem,
    Candidate,
    KeyEntry,
    Stratum,
)


def allocate(available: Mapping[Stratum, int], total: int) -> dict[Stratum, int]:
    if total <= 0:
        raise ValueError(f"total must be positive, got {total}")
    open_strata: list[Stratum] = [s for s in STRATA if available.get(s, 0) > 0]
    quota: dict[Stratum, int] = dict.fromkeys(open_strata, 0)
    left = min(total, sum(available[s] for s in open_strata))
    while left > 0:
        hungry: list[Stratum] = [s for s in open_strata if quota[s] < available[s]]
        share, extra = divmod(left, len(hungry))
        for index, stratum in enumerate(hungry):
            want = share + (1 if index < extra else 0)
            take = min(want, available[stratum] - quota[stratum])
            quota[stratum] += take
            left -= take
    return quota


def sample_items(
    candidates: Sequence[Candidate], *, total: int, seed: int
) -> tuple[list[BlindItem], list[KeyEntry]]:
    by_stratum: dict[Stratum, list[Candidate]] = {}
    for c in candidates:
        by_stratum.setdefault(c.stratum, []).append(c)
    quota = allocate({s: len(cs) for s, cs in by_stratum.items()}, total)
    chosen = [c for s, n in quota.items() for c in _spread(by_stratum[s], seed)[:n]]
    pairs = sorted(((_item_id(c, seed), c) for c in chosen), key=lambda pair: pair[0])
    ids = [item_id for item_id, _ in pairs]
    if len(set(ids)) != len(ids):
        raise ValueError("two sampled answers share an id; the pool holds a duplicate record")
    items = [_blind(item_id, c) for item_id, c in pairs]
    key = [_key(item_id, c) for item_id, c in pairs]
    return items, key


def _spread(candidates: Sequence[Candidate], seed: int) -> list[Candidate]:
    """Round-robin over systems, each system's answers in seeded-hash order."""
    groups: dict[str, list[Candidate]] = {}
    for c in candidates:
        groups.setdefault(f"{c.origin}/{c.system}", []).append(c)
    ranked = [sorted(groups[g], key=lambda c: _digest(c, seed)) for g in sorted(groups)]
    out: list[Candidate] = []
    for depth in range(max(len(r) for r in ranked)):
        out += [r[depth] for r in ranked if depth < len(r)]
    return out


def _digest(c: Candidate, seed: int) -> str:
    text = f"{seed}:{c.origin}:{c.system}:{c.record_id}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _item_id(c: Candidate, seed: int) -> str:
    return "gj-" + hashlib.sha256(f"id:{_digest(c, seed)}".encode()).hexdigest()[:12]


def _blind(item_id: str, c: Candidate) -> BlindItem:
    return BlindItem(
        id=item_id, turns=c.turns, asked_on=c.asked_on, answer=c.answer, sources=c.sources
    )


def _key(item_id: str, c: Candidate) -> KeyEntry:
    return KeyEntry(
        id=item_id,
        origin=c.origin,
        record_id=c.record_id,
        system=c.system,
        model=c.model,
        stratum=c.stratum,
        grader_error=c.grader_error,
        grader_verdict="correct" if c.stratum == "correct" else "incorrect",
    )
