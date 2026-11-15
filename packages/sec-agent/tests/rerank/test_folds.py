"""Cross-validation by company: no fold trains on the company it is scored on."""

import datetime as dt

import pytest

from sec_agent.golden.gret.models import ChunkRef, Label, PoolItem, RetQuestion
from sec_agent.rerank.folds import Fold, company_folds, pool_texts, training_pairs

T = dt.datetime(2026, 11, 13, tzinfo=dt.UTC)


def _question(qid: str, ticker: str) -> RetQuestion:
    return RetQuestion(id=qid, ticker=ticker, question=f"question {qid}", written_on=T.date())


def _item(qid: str, ticker: str, ordinal: int, text: str) -> PoolItem:
    return PoolItem(
        qid=qid,
        chunk=ChunkRef(accession="0000000001-24-000001", section="mdna", ordinal=ordinal),
        systems=("hybrid",),
        best_rank=1,
        ticker=ticker,
        index_version="v-test",
        text=text,
        text_sha256=f"{ordinal:064x}",
    )


def _label(item: PoolItem, grade: int, sha: str | None = None) -> Label:
    return Label.model_validate(
        {
            "qid": item.qid,
            "docid": item.docid,
            "grade": grade,
            "text_sha256": sha or item.text_sha256,
            "labeled_at": T,
        }
    )


QUESTIONS = [_question("q1", "AAA"), _question("q2", "BBB"), _question("q3", "CCC")]
POOL = [
    _item("q1", "AAA", 0, "a zero"),
    _item("q1", "AAA", 1, "a one"),
    _item("q2", "BBB", 2, "b two"),
    _item("q3", "CCC", 3, "c three"),
]
LABELS = [_label(POOL[0], 0), _label(POOL[1], 2), _label(POOL[2], 1), _label(POOL[3], 2)]


def test_leave_one_company_out_in_ticker_order() -> None:
    folds = company_folds(["CCC", "AAA", "BBB", "AAA"])
    assert folds == [
        Fold(held_out="AAA", train=("BBB", "CCC")),
        Fold(held_out="BBB", train=("AAA", "CCC")),
        Fold(held_out="CCC", train=("AAA", "BBB")),
    ]
    assert all(f.held_out not in f.train for f in folds)


def test_needs_two_companies() -> None:
    with pytest.raises(ValueError, match="two companies"):
        company_folds(["AAA", "AAA"])


def test_pairs_come_only_from_the_training_companies_with_grade_as_soft_label() -> None:
    pairs = training_pairs(QUESTIONS, POOL, LABELS, tickers={"AAA", "BBB"})
    assert [(p.qid, p.ticker, p.query, p.passage, p.label) for p in pairs] == [
        ("q1", "AAA", "question q1", "a zero", 0.0),
        ("q1", "AAA", "question q1", "a one", 1.0),
        ("q2", "BBB", "question q2", "b two", 0.5),
    ]


def test_a_label_for_other_text_does_not_count() -> None:
    stale = [*LABELS[:2], _label(POOL[2], 1, sha="f" * 64), LABELS[3]]
    with pytest.raises(ValueError, match="1 pooled chunks of the training companies"):
        training_pairs(QUESTIONS, POOL, stale, tickers={"BBB"})


def test_a_pool_item_of_an_unknown_question_is_refused() -> None:
    with pytest.raises(ValueError, match="q9"):
        training_pairs(QUESTIONS, [*POOL, _item("q9", "AAA", 9, "x")], LABELS, tickers={"AAA"})


def test_pool_texts_by_docid() -> None:
    texts = pool_texts(POOL)
    assert texts[POOL[1].docid] == "a one"
    assert len(texts) == 4
