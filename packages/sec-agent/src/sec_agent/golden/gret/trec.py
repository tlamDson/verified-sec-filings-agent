"""TREC text formats: runs (`qid Q0 docid rank score system`) and qrels (`qid 0 docid grade`).

The docid of a chunk is `accession/section/ordinal`; the index version is fixed per pool.
"""

from collections.abc import Iterable

from sec_agent.golden.gret.models import ChunkRef, RunHit


def parse_run(text: str) -> list[RunHit]:
    hits: list[RunHit] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            hits.append(_hit(line))
        except ValueError as error:
            raise ValueError(f"run line {number}: {error}") from error
    return hits


def _hit(line: str) -> RunHit:
    fields = line.split()
    if len(fields) != 6:
        raise ValueError(f"want 6 fields, got {len(fields)}")
    qid, q0, docid, rank, score, system = fields
    if q0 != "Q0":
        raise ValueError(f"second field must be Q0, got {q0!r}")
    return RunHit(
        qid=qid, chunk=ChunkRef.parse(docid), rank=int(rank), score=float(score), system=system
    )


def run_text(hits: Iterable[RunHit]) -> str:
    """Hits as run lines, in the order given; `parse_run` reads them back."""
    return "".join(f"{h.qid} Q0 {h.chunk.docid} {h.rank} {h.score:.6f} {h.system}\n" for h in hits)


def qrels_text(lines: list[str]) -> str:
    return "".join(f"{line}\n" for line in lines)
