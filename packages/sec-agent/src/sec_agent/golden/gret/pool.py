"""Pooling (as TREC does it): label only the union of every system's top k per question.

Chunks no system ranked in its top k count as not relevant. Within a question the pooled
chunks get a seeded order, so the labeller cannot tell which system found a chunk or how
high; questions keep the order of the questions file.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence

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
    pool: list[PoolEntry] = []
    for q in questions:
        entries = [
            PoolEntry(
                qid=q.id,
                chunk=chunk,
                systems=tuple(sorted({h.system for h in chunk_hits})),
                best_rank=min(h.rank for h in chunk_hits),
            )
            for chunk, chunk_hits in found[q.id].items()
        ]
        pool += sorted(entries, key=lambda e: seeded_key(seed, "pool", e.qid, e.chunk.docid))
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
