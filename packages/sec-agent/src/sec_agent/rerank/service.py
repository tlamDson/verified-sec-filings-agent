"""The reranker in the query path: rerank within a time limit, or keep the retrieval order.

Failure mode "reranker slow or down": every call has a timeout; a timeout, a crash or bad
scores count as a failure for a circuit breaker (`llm.breaker`), and while it is open the
scorer is not called. The scorer runs on a fixed pool of worker threads (a bulkhead): when
every worker is busy, for instance still finishing a call that timed out, the call falls
back at once instead of queueing. A fallback is never an error for the caller: the result
says which order it is and why.
"""

import math
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Literal

from sec_agent.llm.breaker import BreakerConfig, BreakerState, CircuitBreaker
from sec_agent.rerank.order import rerank_order
from sec_agent.rerank.scorer import PairScorer

FallbackReason = Literal["breaker_open", "busy", "timeout", "error"]


@dataclass(frozen=True)
class RerankConfig:
    depth: int = 20
    """Retrieval candidates the reranker reorders (the G-ret pool depth)."""
    timeout_seconds: float = 2.0
    workers: int = 1
    breaker: BreakerConfig = field(default_factory=BreakerConfig)

    def __post_init__(self) -> None:
        if self.depth < 1:
            raise ValueError("rerank: depth must be at least 1")
        if not self.timeout_seconds > 0:
            raise ValueError("rerank: timeout_seconds must be positive")
        if self.workers < 1:
            raise ValueError("rerank: workers must be at least 1")


@dataclass(frozen=True)
class RerankResult:
    order: tuple[int, ...]
    """Indices of the input passages, best first; the input order on a fallback."""
    scores: tuple[float, ...] | None
    """One score per input passage, in input order; None on a fallback."""
    fallback: FallbackReason | None


class Reranker:
    def __init__(
        self,
        scorer: PairScorer,
        config: RerankConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._scorer = scorer
        self._config = config or RerankConfig()
        self._breaker = CircuitBreaker(self._config.breaker, clock)
        self._slots = threading.BoundedSemaphore(self._config.workers)
        self._pool = ThreadPoolExecutor(self._config.workers, thread_name_prefix="rerank")

    @property
    def name(self) -> str:
        return self._scorer.name

    @property
    def depth(self) -> int:
        return self._config.depth

    @property
    def breaker_state(self) -> BreakerState:
        return self._breaker.state

    def rerank(self, query: str, passages: Sequence[str]) -> RerankResult:
        if not passages:
            return RerankResult(order=(), scores=None, fallback=None)
        permit = self._breaker.acquire()
        if permit is None:
            return _fallback(passages, "breaker_open")
        if not self._slots.acquire(blocking=False):
            self._breaker.release(permit)
            return _fallback(passages, "busy")
        future = self._pool.submit(self._scorer.score, query, list(passages))
        future.add_done_callback(self._free_slot)
        try:
            scores = future.result(timeout=self._config.timeout_seconds)
            order = _checked_order(scores, len(passages))
        except FutureTimeout:
            self._breaker.failure(permit)
            return _fallback(passages, "timeout")
        except Exception:
            self._breaker.failure(permit)
            return _fallback(passages, "error")
        self._breaker.success(permit)
        return RerankResult(order=tuple(order), scores=tuple(scores), fallback=None)

    def close(self) -> None:
        """Stop the workers; a call still running is not waited for."""
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _free_slot(self, _future: "Future[list[float]]") -> None:
        self._slots.release()


def _checked_order(scores: Sequence[float], n: int) -> list[int]:
    if len(scores) != n:
        raise ValueError(f"reranker gave {len(scores)} scores for {n} passages")
    if not all(math.isfinite(s) for s in scores):
        raise ValueError("reranker gave a score that is not a finite number")
    return rerank_order(scores)


def _fallback(passages: Sequence[str], reason: FallbackReason) -> RerankResult:
    return RerankResult(order=tuple(range(len(passages))), scores=None, fallback=reason)
