"""Reciprocal rank fusion: the reference the SQL fusion is checked against."""

import pytest

from sec_agent.retrieval.rrf import RRF_K, rrf_fuse


def test_score_is_the_sum_of_reciprocal_ranks() -> None:
    fused = dict(rrf_fuse([["a", "b"], ["b", "c"]]))
    assert fused["a"] == 1.0 / (RRF_K + 1)
    assert fused["b"] == 1.0 / (RRF_K + 2) + 1.0 / (RRF_K + 1)
    assert fused["c"] == 1.0 / (RRF_K + 2)


def test_a_passage_found_by_both_rankings_beats_one_found_by_one() -> None:
    assert [key for key, _ in rrf_fuse([["a", "b"], ["b", "c"]])] == ["b", "a", "c"]


def test_ties_break_by_best_rank_then_key() -> None:
    # "x" is first in one list only, "y" first in the other only: equal scores, equal best
    # rank, so the key decides. "z" ties nobody.
    assert [key for key, _ in rrf_fuse([["y", "z"], ["x"]])] == ["x", "y", "z"]
    # Same score 1/(k+1) + 1/(k+3) for both; best rank equal; key decides.
    assert [key for key, _ in rrf_fuse([["q", "p", "r"], ["r", "p", "q"]])][:2] == ["q", "r"]


def test_k_is_a_parameter() -> None:
    assert dict(rrf_fuse([["a"]], k=0))["a"] == 1.0


def test_empty_rankings_fuse_to_nothing() -> None:
    assert rrf_fuse([[], []]) == []


def test_duplicate_key_in_one_ranking_is_rejected() -> None:
    with pytest.raises(ValueError, match="twice"):
        rrf_fuse([["a", "a"]])
