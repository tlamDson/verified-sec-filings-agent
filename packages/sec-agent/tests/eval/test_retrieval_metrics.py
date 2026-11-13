"""recall@k, nDCG@k and MRR@k over graded qrels, and the qrels reader."""

import math

import pytest

from sec_agent.eval.retrieval.metrics import ndcg_at, query_scores, recall_at, reciprocal_rank
from sec_agent.eval.retrieval.qrels import parse_qrels

JUDGED = {"d1": 2, "d2": 1, "d3": 0, "d4": 2}


def test_recall_counts_grade_one_and_up() -> None:
    assert recall_at(["d3", "d1", "x", "d2"], JUDGED, 2) == pytest.approx(1 / 3)
    assert recall_at(["d3", "d1", "x", "d2"], JUDGED, 5) == pytest.approx(2 / 3)


def test_unjudged_and_duplicate_docs_count_once_and_as_not_relevant() -> None:
    assert recall_at(["d1", "d1", "d1", "zz"], JUDGED, 3) == pytest.approx(1 / 3)


def test_ndcg_uses_linear_gain_and_log2_discount() -> None:
    ranking = ["d2", "d1", "d3"]
    dcg = 1 / math.log2(2) + 2 / math.log2(3)
    ideal = 2 / math.log2(2) + 2 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at(ranking, JUDGED, 10) == pytest.approx(dcg / ideal)


def test_ndcg_of_the_ideal_order_is_one() -> None:
    assert ndcg_at(["d1", "d4", "d2"], JUDGED, 10) == pytest.approx(1.0)


def test_ndcg_cuts_the_ideal_at_k_too() -> None:
    assert ndcg_at(["d4"], JUDGED, 1) == pytest.approx(1.0)


def test_reciprocal_rank_of_the_first_relevant_within_k() -> None:
    assert reciprocal_rank(["d3", "x", "d2"], JUDGED, 10) == pytest.approx(1 / 3)
    assert reciprocal_rank(["d3", "x", "d2"], JUDGED, 2) == 0.0


def test_query_without_a_relevant_chunk_has_no_scores() -> None:
    assert query_scores(["d1"], {"d1": 0}) is None


def test_query_scores_names_the_plan_metrics() -> None:
    scores = query_scores(["d1", "d4", "d2"], JUDGED)
    assert scores is not None
    assert scores == {"recall@5": 1.0, "ndcg@10": pytest.approx(1.0), "mrr@10": 1.0}


def test_parse_qrels() -> None:
    text = "q1 0 a/b/0 2\n\nq1 0 a/b/1 0\nq2 0 a/b/0 1\n"
    assert parse_qrels(text) == {"q1": {"a/b/0": 2, "a/b/1": 0}, "q2": {"a/b/0": 1}}


@pytest.mark.parametrize("line", ["q1 0 d 3", "q1 0 d", "q1 0 d x", "q1 0 d 1\nq1 0 d 2"])
def test_parse_qrels_rejects_bad_lines(line: str) -> None:
    with pytest.raises(ValueError, match="qrels line"):
        parse_qrels(line)
