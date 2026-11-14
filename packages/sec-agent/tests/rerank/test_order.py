"""rerank_order: indices best first by score, ties kept in retrieval order."""

import math

import pytest

from sec_agent.rerank.order import rerank_order


def test_higher_score_first() -> None:
    assert rerank_order([0.1, 0.9, 0.5]) == [1, 2, 0]


def test_ties_keep_the_retrieval_order() -> None:
    assert rerank_order([0.5, 0.7, 0.5, 0.7]) == [1, 3, 0, 2]


def test_empty() -> None:
    assert rerank_order([]) == []


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_refuses_scores_that_are_not_finite(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        rerank_order([0.1, bad])
