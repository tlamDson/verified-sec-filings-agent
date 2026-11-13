"""LLMRouter with two calls to one provider in flight: the outcome that arrives last
belongs to the call that was sent first, and must not undo what the breaker learned since.

A scripted reply (simulated model) makes a second call through the router before it
returns, so the first call's outcome arrives after the second call's, with no threads.
"""

from collections.abc import Callable

from llm_fakes import Clock, ScriptedProvider, says

from sec_agent.llm.breaker import BreakerConfig
from sec_agent.llm.errors import ProviderRateLimitedError, ProviderUnavailableError
from sec_agent.llm.messages import ChatRequest, Message
from sec_agent.llm.quota import MemoryQuotaStore
from sec_agent.llm.router import LLMRouter

REQUEST = ChatRequest(messages=[{"role": "user", "content": "question"}])
INNER = ChatRequest(messages=[{"role": "user", "content": "sent while the first is out"}])
DOWN = ProviderUnavailableError("503 from provider")


class _Harness:
    """Provider `a` under test and a backup `b` that always answers."""

    def __init__(self) -> None:
        self.clock = Clock()
        self.a = ScriptedProvider("a")
        self.b = ScriptedProvider("b", [says("b") for _ in range(8)])
        self.router = LLMRouter(
            [self.a, self.b],
            quota=MemoryQuotaStore(),
            breaker=BreakerConfig(failure_threshold=2, cooldown_seconds=30.0),
            clock=self.clock.monotonic,
            now=self.clock.now,
        )

    def while_out(
        self, then: Message | Exception, calls: int = 1
    ) -> Callable[[ChatRequest], Message]:
        """A reply of `a` that sends `calls` more requests before its own outcome arrives."""

        def reply(request: ChatRequest) -> Message:
            for _ in range(calls):
                self.router.complete(INNER)
            if isinstance(then, Exception):
                raise then
            return then

        return reply

    def first_attempt(self) -> str:
        return self.router.complete(REQUEST).attempts[0].outcome


def test_a_slow_success_does_not_cancel_the_wait_a_429_asked_meanwhile() -> None:
    h = _Harness()
    h.a.then(
        h.while_out(says("slow answer")),
        ProviderRateLimitedError("429 from provider", retry_after=600.0),
        says("back"),
    )
    assert h.router.complete(REQUEST).provider == "a", "the slow call itself is answered"
    assert h.router.breaker_state("a") == "open"
    h.clock.advance(599)
    assert h.first_attempt() == "breaker_open"
    h.clock.advance(1)
    assert h.router.complete(REQUEST).provider == "a"
    assert len(h.a.requests) == 3


def test_a_slow_failure_does_not_replace_a_429_wait_with_the_cooldown() -> None:
    h = _Harness()
    h.a.then(
        h.while_out(DOWN),
        ProviderRateLimitedError("429 from provider", retry_after=600.0),
        says("back"),
    )
    h.router.complete(REQUEST)
    h.clock.advance(30)  # the cooldown a counted failure starts
    assert h.first_attempt() == "breaker_open"
    h.clock.advance(569)
    assert h.first_attempt() == "breaker_open"
    h.clock.advance(1)
    assert h.router.complete(REQUEST).provider == "a"


def test_a_slow_429_with_a_short_wait_does_not_shorten_a_longer_one() -> None:
    h = _Harness()
    h.a.then(
        h.while_out(ProviderRateLimitedError("429 from provider", retry_after=5.0)),
        ProviderRateLimitedError("429 from provider", retry_after=600.0),
        says("back"),
    )
    h.router.complete(REQUEST)
    h.clock.advance(599)
    assert h.first_attempt() == "breaker_open"
    h.clock.advance(1)
    assert h.router.complete(REQUEST).provider == "a"


def test_a_slow_success_does_not_close_a_breaker_that_failures_opened_meanwhile() -> None:
    h = _Harness()
    h.a.then(h.while_out(says("slow answer"), calls=2), DOWN, DOWN, says("back"))
    assert h.router.complete(REQUEST).provider == "a"
    assert h.router.breaker_state("a") == "open"
    assert h.first_attempt() == "breaker_open"
    h.clock.advance(30)
    assert h.router.complete(REQUEST).provider == "a"
    assert h.router.breaker_state("a") == "closed"
