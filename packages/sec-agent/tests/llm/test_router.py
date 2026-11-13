"""LLMRouter: providers in order, with a quota count and a circuit breaker for each.

The providers are scripted (simulated models); no model or network is called.
"""

import pytest
from llm_fakes import Clock, ScriptedProvider, says

from sec_agent.llm.breaker import BreakerConfig
from sec_agent.llm.errors import (
    AllProvidersFailedError,
    LLMConfigError,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from sec_agent.llm.messages import ChatRequest, Usage
from sec_agent.llm.quota import MemoryQuotaStore, QuotaLimits, QuotaUsage
from sec_agent.llm.router import Attempt, LLMRouter

REQUEST = ChatRequest(messages=[{"role": "user", "content": "question"}])
DOWN = ProviderUnavailableError("503 from provider")


def _router(
    *providers: ScriptedProvider, clock: Clock | None = None, quota: MemoryQuotaStore | None = None
) -> LLMRouter:
    clock = clock or Clock()
    return LLMRouter(
        providers,
        quota=quota or MemoryQuotaStore(),
        breaker=BreakerConfig(failure_threshold=2, cooldown_seconds=30.0),
        clock=clock.monotonic,
        now=clock.now,
    )


def test_the_first_provider_answers_and_the_next_is_not_called() -> None:
    a, b = ScriptedProvider("a", [says("from a")]), ScriptedProvider("b")
    result = _router(a, b).complete(REQUEST)
    assert result.provider == "a"
    assert result.completion.message["content"] == "from a"
    assert result.attempts == (Attempt("a", "ok", ""),)
    assert a.requests == [REQUEST]
    assert b.requests == []


def test_an_unavailable_provider_fails_over_to_the_next_in_order() -> None:
    a = ScriptedProvider("a", [DOWN])
    b = ScriptedProvider("b", [ProviderResponseError("not a chat completion")])
    c = ScriptedProvider("c", [says("from c")])
    result = _router(a, b, c).complete(REQUEST)
    assert result.provider == "c"
    assert [(x.provider, x.outcome) for x in result.attempts] == [
        ("a", "unavailable"),
        ("b", "bad_response"),
        ("c", "ok"),
    ]
    assert result.attempts[0].detail == "503 from provider"


def test_a_provider_out_of_quota_is_skipped_without_a_call() -> None:
    clock = Clock()
    a = ScriptedProvider("a", [says("one")], limits=QuotaLimits(requests_per_day=1))
    b = ScriptedProvider("b", [says("two")])
    router = _router(a, b, clock=clock)
    assert router.complete(REQUEST).provider == "a"
    result = router.complete(REQUEST)
    assert result.provider == "b"
    assert [(x.provider, x.outcome) for x in result.attempts] == [
        ("a", "quota_exhausted"),
        ("b", "ok"),
    ]
    assert len(a.requests) == 1


def test_each_call_counts_one_request_and_its_tokens_for_the_provider_that_ran() -> None:
    clock, quota = Clock(), MemoryQuotaStore()
    a = ScriptedProvider("a", [DOWN])
    b = ScriptedProvider("b", [says("ok")], usage=Usage(prompt_tokens=900, completion_tokens=31))
    _router(a, b, clock=clock, quota=quota).complete(REQUEST)
    assert quota.usage("a", clock.now()) == QuotaUsage(1, 1, 0), "a failed call still used a slot"
    assert quota.usage("b", clock.now()) == QuotaUsage(1, 1, 931)


def test_repeated_failures_open_the_breaker_and_the_provider_is_left_alone() -> None:
    clock = Clock()
    a = ScriptedProvider("a", [DOWN, DOWN])
    b = ScriptedProvider("b", [says("1"), says("2"), says("3")])
    router = _router(a, b, clock=clock)
    router.complete(REQUEST)
    router.complete(REQUEST)
    assert router.breaker_state("a") == "open"
    result = router.complete(REQUEST)
    assert [(x.provider, x.outcome) for x in result.attempts] == [
        ("a", "breaker_open"),
        ("b", "ok"),
    ]
    assert len(a.requests) == 2


def test_after_the_cooldown_the_provider_is_probed_and_recovers() -> None:
    clock = Clock()
    a = ScriptedProvider("a", [DOWN, DOWN, says("back")])
    b = ScriptedProvider("b", [says("1"), says("2")])
    router = _router(a, b, clock=clock)
    router.complete(REQUEST)
    router.complete(REQUEST)
    clock.advance(30)
    result = router.complete(REQUEST)
    assert result.provider == "a"
    assert router.breaker_state("a") == "closed"


def test_a_probe_refused_by_quota_does_not_use_up_the_trial() -> None:
    clock = Clock()
    a = ScriptedProvider("a", [DOWN, DOWN, says("back")], limits=QuotaLimits(requests_per_minute=2))
    b = ScriptedProvider("b", [says("1"), says("2"), says("3")])
    router = _router(a, b, clock=clock)
    router.complete(REQUEST)
    router.complete(REQUEST)
    clock.advance(30)  # breaker half-open, but the minute's two requests are spent
    assert router.complete(REQUEST).attempts[0] == Attempt("a", "quota_exhausted", "")
    clock.advance(60)
    assert router.complete(REQUEST).provider == "a"


def test_429_opens_the_breaker_at_once_for_the_wait_the_provider_asked() -> None:
    clock = Clock()
    a = ScriptedProvider(
        "a", [ProviderRateLimitedError("429 from provider", retry_after=120.0), says("back")]
    )
    b = ScriptedProvider("b", [says("1"), says("2")])
    router = _router(a, b, clock=clock)
    first = router.complete(REQUEST)
    assert [(x.provider, x.outcome) for x in first.attempts] == [("a", "rate_limited"), ("b", "ok")]
    assert router.breaker_state("a") == "open"
    clock.advance(119)
    assert router.complete(REQUEST).attempts[0].outcome == "breaker_open"
    clock.advance(1)
    assert router.complete(REQUEST).provider == "a"


def test_a_rejected_request_fails_over_but_does_not_count_against_the_provider() -> None:
    rejected = ProviderRejectedError("400 from provider")
    a = ScriptedProvider("a", [rejected, rejected, rejected, says("fine")])
    b = ScriptedProvider("b", [says("1"), says("2"), says("3")])
    router = _router(a, b)
    for _ in range(3):
        result = router.complete(REQUEST)
        assert [(x.provider, x.outcome) for x in result.attempts] == [
            ("a", "rejected"),
            ("b", "ok"),
        ]
    assert router.breaker_state("a") == "closed"
    assert router.complete(REQUEST).provider == "a"


def test_when_every_provider_fails_the_error_says_what_each_one_did() -> None:
    a = ScriptedProvider("a", [DOWN], limits=QuotaLimits(requests_per_day=5))
    b = ScriptedProvider("b", limits=QuotaLimits(requests_per_day=1))
    quota, clock = MemoryQuotaStore(), Clock()
    quota.reserve("b", b.limits, clock.now())
    with pytest.raises(AllProvidersFailedError) as caught:
        _router(a, b, clock=clock, quota=quota).complete(REQUEST)
    assert caught.value.attempts == (
        Attempt("a", "unavailable", "503 from provider"),
        Attempt("b", "quota_exhausted", ""),
    )
    assert "a: unavailable" in str(caught.value)
    assert "b: quota_exhausted" in str(caught.value)


def test_a_bug_in_a_provider_is_not_swallowed() -> None:
    a = ScriptedProvider("a", [ValueError("bug")])
    with pytest.raises(ValueError, match="bug"):
        _router(a, ScriptedProvider("b", [says("x")])).complete(REQUEST)


def test_a_router_needs_providers_with_distinct_names() -> None:
    with pytest.raises(LLMConfigError, match="no provider"):
        _router()
    with pytest.raises(LLMConfigError, match="twice"):
        _router(ScriptedProvider("a"), ScriptedProvider("a"))
    with pytest.raises(KeyError):
        _router(ScriptedProvider("a")).breaker_state("b")
