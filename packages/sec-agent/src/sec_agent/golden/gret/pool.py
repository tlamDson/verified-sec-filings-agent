"""Pooling (as TREC does it): label only the union of every system's top k per question.

Chunks no system ranked in its top k count as not relevant. Within a question the pooled
chunks get a seeded order, so the labeller cannot tell which system found a chunk or how
high; questions keep the order of the questions file.
"""

from collections import defaultdict
from collections.abc import Container, Mapping, Sequence

from sec_agent.golden.gret.models import (
    ChunkRef,
    ChunkText,
    PoolEntry,
    PoolItem,
    RetQuestion,
    RunHit,
)
from sec_agent.golden.ranking import seeded_key

DEFAULT_DEPTH = 20


def build_pool(
    questions: Sequence[RetQuestion], hits: Sequence[RunHit], *, depth: int, seed: int
) -> list[PoolEntry]:
    known = {q.id for q in questions}
    unknown = sorted({h.qid for h in hits} - known)
    if unknown:
        raise ValueError(f"runs have hits for questions not in the questions file: {unknown}")
    ranked: defaultdict[tuple[str, str], list[RunHit]] = defaultdict(list)
    for hit in hits:
        ranked[(hit.qid, hit.system)].append(hit)
    found: defaultdict[str, dict[ChunkRef, list[RunHit]]] = defaultdict(dict)
    for (qid, _), system_hits in ranked.items():
        for hit in sorted(system_hits, key=lambda h: (h.rank, h.chunk.docid))[:depth]:
            found[qid].setdefault(hit.chunk, []).append(hit)
    entries = [
        PoolEntry(
            qid=qid,
            chunk=chunk,
            systems=tuple(sorted({h.system for h in chunk_hits})),
            best_rank=min(h.rank for h in chunk_hits),
        )
        for qid, chunks in found.items()
        for chunk, chunk_hits in chunks.items()
    ]
    return _ordered(questions, entries, seed)


def extend_pool(
    previous: Sequence[PoolItem],
    fresh: Sequence[PoolEntry],
    questions: Sequence[RetQuestion],
    *,
    seed: int,
    in_index: Container[ChunkRef],
) -> tuple[list[PoolEntry], list[PoolEntry]]:
    """Grow a pool with the top k of new runs (on a new index version, or new systems).

    Every previously pooled chunk stays while the new index still has it, so its label
    carries over when its text is unchanged (labels are tied to the text's hash) and it is
    pending again when the text changed. Return (pool, previous entries dropped because the
    index no longer has their chunk). A chunk pooled again keeps the new runs' systems and
    rank; one the new runs missed keeps its old ones. Order is that of `build_pool`.
    """
    known = {q.id for q in questions}
    unknown = sorted({i.qid for i in previous} - known)
    if unknown:
        raise ValueError(f"previous pool has questions not in the questions file: {unknown}")
    merged = {(e.qid, e.chunk): e for e in fresh}
    dropped: list[PoolEntry] = []
    for item in previous:
        key = (item.qid, item.chunk)
        if key in merged:
            continue
        entry = PoolEntry(
            qid=item.qid, chunk=item.chunk, systems=item.systems, best_rank=item.best_rank
        )
        if item.chunk in in_index:
            merged[key] = entry
        else:
            dropped.append(entry)
    return _ordered(questions, list(merged.values()), seed), dropped


def _ordered(
    questions: Sequence[RetQuestion], entries: Sequence[PoolEntry], seed: int
) -> list[PoolEntry]:
    """Questions in file order; within one, a seeded order that hides system and rank."""
    by_question: defaultdict[str, list[PoolEntry]] = defaultdict(list)
    for entry in entries:
        by_question[entry.qid].append(entry)
    pool: list[PoolEntry] = []
    for q in questions:
        chunks = by_question[q.id]
        pool += sorted(chunks, key=lambda e: seeded_key(seed, "pool", e.qid, e.chunk.docid))
    return pool


def attach_text(
    entries: Sequence[PoolEntry],
    texts: Mapping[ChunkRef, ChunkText],
    questions: Sequence[RetQuestion],
    *,
    index_version: str,
) -> list[PoolItem]:
    missing = sorted({e.chunk.docid for e in entries if e.chunk not in texts})
    if missing:
        shown = ", ".join(missing[:5])
        raise ValueError(f"{len(missing)} pooled chunks missing from {index_version}: {shown}")
    tickers = {q.id: q.ticker for q in questions}
    return [
        PoolItem(
            **e.model_dump(),
            ticker=tickers[e.qid],
            index_version=index_version,
            text=texts[e.chunk].text,
            text_sha256=texts[e.chunk].text_sha256,
        )
        for e in entries
    ]
