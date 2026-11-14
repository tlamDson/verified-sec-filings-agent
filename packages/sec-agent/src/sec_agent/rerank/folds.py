"""Cross-validation by company for the reranker, and its training pairs from the G-ret pool.

G-ret labels exist only for the 10 test companies, so the reranker is fine-tuned by
leave-one-company-out: the model that scores a company's questions never saw a label of
that company. The training pairs are every labelled pool item of the training companies,
with the grade (0, 1, 2) as a soft label grade / 2.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.golden.gret.labels import current_labels, pending_items
from sec_agent.golden.gret.models import Label, PoolItem, RetQuestion


@dataclass(frozen=True)
class Fold:
    held_out: str
    train: tuple[str, ...]


class TrainPair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    qid: str
    ticker: str
    query: str
    passage: str
    label: float = Field(ge=0.0, le=1.0)


def company_folds(tickers: Iterable[str]) -> list[Fold]:
    """One fold per company, in ticker order, training on all the others."""
    companies = sorted(set(tickers))
    if len(companies) < 2:
        raise ValueError("cross-validation by company needs at least two companies")
    return [Fold(held_out=c, train=tuple(o for o in companies if o != c)) for c in companies]


def training_pairs(
    questions: Sequence[RetQuestion],
    pool: Sequence[PoolItem],
    labels: Iterable[Label],
    *,
    tickers: Collection[str],
) -> list[TrainPair]:
    """Pairs of the questions about `tickers`, in pool order. Every pooled chunk of those
    questions must carry a current label (one given for its exact text)."""
    by_id = {q.id: q for q in questions}
    if unknown := sorted({item.qid for item in pool} - set(by_id)):
        raise ValueError(f"pool items for questions not in the questions file: {unknown}")
    chosen = [item for item in pool if by_id[item.qid].ticker in tickers]
    all_labels = list(labels)
    if pending := pending_items(chosen, all_labels):
        raise ValueError(
            f"{len(pending)} pooled chunks of the training companies have no current label"
        )
    current = current_labels(all_labels)
    return [
        TrainPair(
            qid=item.qid,
            ticker=by_id[item.qid].ticker,
            query=by_id[item.qid].question,
            passage=item.text,
            label=current[(item.qid, item.docid)].grade / 2,
        )
        for item in chosen
    ]


def pool_texts(pool: Iterable[PoolItem]) -> dict[str, str]:
    """docid -> chunk text. One index version has one text per chunk."""
    texts: dict[str, str] = {}
    for item in pool:
        if texts.setdefault(item.docid, item.text) != item.text:
            raise ValueError(f"pool has two texts for {item.docid}: mixed index versions?")
    return texts
