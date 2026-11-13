"""Relevance labels: an append-only file where the latest label of a chunk wins.

A label counts only while the pooled chunk still has the text it was given for (same
SHA-256); a re-chunked index makes old labels stale, and those chunks are pending again.
"""

from collections.abc import Iterable, Sequence

from sec_agent.golden.gret.models import Label, PoolItem


def current_labels(labels: Iterable[Label]) -> dict[tuple[str, str], Label]:
    out: dict[tuple[str, str], Label] = {}
    for label in sorted(labels, key=lambda lbl: lbl.labeled_at):
        out[(label.qid, label.docid)] = label
    return out


def _labelled(item: PoolItem, current: dict[tuple[str, str], Label]) -> Label | None:
    label = current.get((item.qid, item.docid))
    return label if label is not None and label.text_sha256 == item.text_sha256 else None


def pending_items(pool: Sequence[PoolItem], labels: Iterable[Label]) -> list[PoolItem]:
    current = current_labels(labels)
    return [item for item in pool if _labelled(item, current) is None]


def qrels_lines(pool: Sequence[PoolItem], labels: Iterable[Label]) -> list[str]:
    """`qid 0 docid grade` for each pooled chunk with a current label, in pool order."""
    current = current_labels(labels)
    out: list[str] = []
    for item in pool:
        label = _labelled(item, current)
        if label is not None:
            out.append(f"{item.qid} 0 {item.docid} {label.grade}")
    return out
