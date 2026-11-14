"""Reranker service: rerank within a time limit, or fall back to the retrieval order.

Failures (timeout, crash, bad scores) count towards a circuit breaker; while it is open
the scorer is not called at all. A call never waits for a busy scorer.
"""

import math
from collections.abc import Sequence

import pytest
from llm_fakes import Clock
from rerank_kit import BlockingScorer, BrokenScorer, FakeScorer, by_length

from sec_agent.llm.breaker import BreakerConfig
from sec_agent.rerank.service import RerankConfig, Reranker

PASSAGES = ["aa", "a", "aaaa", "aaa"]
FAST = RerankConfig(
    timeout_seconds=0.05,
    workers=1,
    breaker=BreakerConfig(failure_threshold=2, cooldown_seconds=30.0),
)


def _reranker(scorer: object, clock: Clock | None = None) -> Reranker:
    return Reranker(scorer, FAST, clock=(clock or Clock()).monotonic)  # pyright: ignore[reportArgumentType]


def test_orders_by_score() -> None:
    reranker = _reranker(FakeScorer(by_length, name="len"))
    result = reranker.rerank("q", PASSAGES)
    assert result.order == (2, 3, 0, 1)
    assert result.scores == (2.0, 1.0, 4.0, 3.0)
    assert result.fallback is None
    assert reranker.name == "len"


def test_no_passages_no_call() -> None:
    scorer = FakeScorer(by_length)
    result = _reranker(scorer).rerank("q", [])
    assert result.order == ()
    assert result.fallback is None
    assert scorer.calls == []


def test_a_slow_scorer_times_out_to_the_retrieval_order() -> None:
    scorer = BlockingScorer()
    reranker = _reranker(scorer)
    try:
        result = reranker.rerank("q", PASSAGES)
        assert result.order == (0, 1, 2, 3)
        assert result.scores is None
        assert result.fallback == "timeout"
    finally:
        scorer.release.set()
        reranker.close()


def test_a_scorer_still_busy_is_not_waited_for() -> None:
    scorer = BlockingScorer()
    reranker = _reranker(scorer)
    try:
        assert reranker.rerank("q", PASSAGES).fallback == "timeout"
        assert reranker.rerank("q", PASSAGES).fallback == "busy"
    finally:
        scorer.release.set()
        reranker.close()


def test_a_crash_falls_back() -> None:
    result = _reranker(BrokenScorer()).rerank("q", PASSAGES)
    assert result.fallback == "error"
    assert result.order == (0, 1, 2, 3)


def _short(passages: Sequence[str]) -> list[float]:
    return [1.0 for _ in passages][1:]


def _nan(passages: Sequence[str]) -> list[float]:
    return [math.nan for _ in passages]


@pytest.mark.parametrize("answer", [_short, _nan])
def test_bad_scores_fall_back(answer: object) -> None:
    result = _reranker(BrokenScorer(answer)).rerank("q", PASSAGES)  # pyright: ignore[reportArgumentType]
    assert result.fallback == "error"


def test_failures_open_the_breaker_then_one_trial_closes_it() -> None:
    clock = Clock()
    healthy = {"now": False}

    def flaky(_q: str, p: str) -> float:
        if not healthy["now"]:
            raise RuntimeError("down")
        return float(len(p))

    scorer = FakeScorer(flaky)
    reranker = _reranker(scorer, clock)
    assert reranker.rerank("q", PASSAGES).fallback == "error"
    assert reranker.rerank("q", PASSAGES).fallback == "error"
    assert reranker.breaker_state == "open"
    calls = len(scorer.calls)
    assert reranker.rerank("q", PASSAGES).fallback == "breaker_open"
    assert len(scorer.calls) == calls
    clock.advance(30.0)
    healthy["now"] = True
    assert reranker.rerank("q", PASSAGES).fallback is None
    assert reranker.breaker_state == "closed"


def test_config_is_checked() -> None:
    with pytest.raises(ValueError, match="timeout"):
        RerankConfig(timeout_seconds=0)
    with pytest.raises(ValueError, match="workers"):
        RerankConfig(workers=0)
    with pytest.raises(ValueError, match="depth"):
        RerankConfig(depth=0)
