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


def labels_by_text(labels: Iterable[Label]) -> dict[tuple[str, str, str], Label]:
    """Latest label per (qid, docid, text hash). Two index versions may pool one docid with
    different text; each keeps the label given for its own text."""
    out: dict[tuple[str, str, str], Label] = {}
    for label in sorted(labels, key=lambda lbl: lbl.labeled_at):
        out[(label.qid, label.docid, label.text_sha256)] = label
    return out


def label_for(item: PoolItem, by_text: dict[tuple[str, str, str], Label]) -> Label | None:
    return by_text.get((item.qid, item.docid, item.text_sha256))


def pending_items(pool: Sequence[PoolItem], labels: Iterable[Label]) -> list[PoolItem]:
    current = labels_by_text(labels)
    return [item for item in pool if label_for(item, current) is None]


def qrels_lines(pool: Sequence[PoolItem], labels: Iterable[Label]) -> list[str]:
    """`qid 0 docid grade` for each pooled chunk with a current label, in pool order."""
    current = labels_by_text(labels)
    out: list[str] = []
    for item in pool:
        label = label_for(item, current)
        if label is not None:
            out.append(f"{item.qid} 0 {item.docid} {label.grade}")
    return out
