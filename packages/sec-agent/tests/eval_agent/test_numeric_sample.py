"""`eval answer --limit N`: a short night samples every question type, not the file's head."""

from collections import Counter

import pytest
from eval_data import number_question

from sec_agent.eval.numeric.sample import stratified
from sec_agent.golden.gnum.models import NumQuestion

TYPES = ("value", "yoy_growth", "ratio", "fiscal_period")


def questions(per_type: int) -> list[NumQuestion]:
    """Simulated questions, listed type by type as the G-num file lists them."""
    return [
        number_question(f"{qtype}-{i}", "1", qtype=qtype)
        for qtype in TYPES
        for i in range(per_type)
    ]


def test_the_limit_is_shared_by_every_question_type() -> None:
    picked = stratified(questions(10), 20)
    assert Counter(q.qtype for q in picked) == {t: 5 for t in TYPES}


def test_a_longer_night_keeps_every_question_of_a_shorter_one() -> None:
    pool = questions(10)
    short, long = stratified(pool, 12), stratified(pool, 30)
    assert {q.id for q in short} <= {q.id for q in long}
    assert len(long) == 30


def test_picked_questions_keep_file_order_and_the_limit_caps_at_the_pool() -> None:
    pool = questions(3)
    assert stratified(pool, 100) == pool
    picked = stratified(pool, 6)
    assert picked == [q for q in pool if q in picked]


def test_a_negative_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        stratified(questions(1), -1)
