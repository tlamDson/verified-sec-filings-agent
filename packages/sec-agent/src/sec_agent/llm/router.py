"""LLMRouter: the one way the agent calls a model.

Providers are tried in the order given. For each: the circuit breaker must allow a call,
then the quota must have room for the request and for the tokens the call can use at
most (`token_bound`), which are held while it runs; a provider that fails is noted and
the next one is tried. When none answers, `AllProvidersFailedError` carries what each one
did, and the agent falls back to its degraded answer.

Each call made to a provider is a `chat` span; a provider passed over without a call is
an event on the caller's span (`observability.spans`).
"""

import datetime as dt
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from opentelemetry.trace import Tracer

from sec_agent.llm.attempts import Attempt, Outcome
from sec_agent.llm.breaker import BreakerConfig, BreakerState, CircuitBreaker, Permit
from sec_agent.llm.errors import (
    AllProvidersFailedError,
    LLMConfigError,
    ProviderError,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderResponseError,
)
from sec_agent.llm.messages import ChatRequest, Completion, Usage
from sec_agent.llm.provider import Provider
from sec_agent.llm.quota import QuotaStore
from sec_agent.llm.token_bound import token_bound
from sec_agent.observability.spans import (
    chat_answered,
    chat_span,
    default_tracer,
    failed,
    provider_skipped,
)

__all__ = ["Attempt", "LLMRouter", "RouterResult"]

DEFAULT_MAX_TOKENS = 1024
_SPENT_NOTHING: frozenset[Outcome] = frozenset({"rate_limited", "rejected"})


@dataclass(frozen=True)
class RouterResult:
    provider: str
    completion: Completion
    attempts: tuple[Attempt, ...]
    """Every provider tried for this request, in order; the last one is `ok`."""


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class LLMRouter:
    def __init__(
        self,
        providers: Sequence[Provider],
        *,
        quota: QuotaStore,
        breaker: BreakerConfig | None = None,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], dt.datetime] = _utc_now,
        tracer: Tracer | None = None,
    ) -> None:
        """`default_max_tokens` is the output limit given to a request that has none when
        it goes to a provider with a daily token quota: without one, the call's tokens
        have no bound to hold."""
        if not providers:
            raise LLMConfigError("no provider is configured")
        if default_max_tokens < 1:
            raise LLMConfigError("default_max_tokens must be positive")
        config = breaker or BreakerConfig()
        self._providers = tuple(providers)
        self._quota = quota
        self._default_max_tokens = default_max_tokens
        self._now = now
        self._tracer = tracer or default_tracer()
        self._breakers: dict[str, CircuitBreaker] = {}
        for provider in self._providers:
            if provider.name in self._breakers:
                raise LLMConfigError(f"provider {provider.name!r} is configured twice")
            self._breakers[provider.name] = CircuitBreaker(config, clock)

    def breaker_state(self, provider: str) -> BreakerState:
        """KeyError when no provider has that name."""
        return self._breakers[provider].state

    def complete(self, request: ChatRequest) -> RouterResult:
        attempts: list[Attempt] = []
        for provider in self._providers:
            completion = self._try(provider, request, attempts)
            if completion is not None:
                return RouterResult(provider.name, completion, tuple(attempts))
        raise AllProvidersFailedError(tuple(attempts))

    def _try(
        self, provider: Provider, request: ChatRequest, attempts: list[Attempt]
    ) -> Completion | None:
        name, breaker = provider.name, self._breakers[provider.name]
        permit = breaker.acquire()
        if permit is None:
            attempts.append(Attempt(name, "breaker_open", ""))
            provider_skipped(name, "breaker_open")
            return None
        request, hold = self._bounded(provider, request)
        reserved_at = self._now()
        try:
            reserved = self._quota.reserve(name, provider.limits, reserved_at, hold)
        except BaseException:  # the count is unreachable: no call was made
            breaker.release(permit)
            raise
        if not reserved:
            breaker.release(permit)
            attempts.append(Attempt(name, "quota_exhausted", ""))
            provider_skipped(name, "quota_exhausted")
            return None
        with chat_span(self._tracer, name, request) as span:
            try:
                completion = provider.complete(request)
            except ProviderError as error:
                outcome = _settle_breaker(breaker, permit, error)
                if outcome in _SPENT_NOTHING:  # refused before any token was generated
                    self._quota.settle(name, reserved_at, held=hold, used=0)
                # otherwise (timeout, 5xx, broken reply) the provider may have spent tokens
                # nobody reported: the hold stays, so the count can only err on the safe side
                attempts.append(Attempt(name, outcome, str(error)))
                failed(span, outcome)  # the outcome code only: the error's text stays here
                return None
            except BaseException:  # a bug or a cancel says nothing about the provider
                breaker.release(permit)  # the hold stays: the call went out, its cost is unknown
                raise
            chat_answered(span, completion)
        breaker.success(permit)
        self._quota.settle(name, reserved_at, held=hold, used=_charge(completion.usage, hold))
        attempts.append(Attempt(name, "ok", ""))
        return completion

    def _bounded(self, provider: Provider, request: ChatRequest) -> tuple[ChatRequest, int]:
        """The request as this provider gets it, and the tokens to hold for it.

        Only a provider with a daily token quota needs a hold; for it, a request without
        an output limit gets the default one, so that its tokens have a bound.
        """
        if provider.limits.tokens_per_day is None:
            return request, 0
        if request.max_tokens is None:
            request = replace(request, max_tokens=self._default_max_tokens)
        bound = token_bound(request)
        if bound is None:  # unreachable: the request has an output limit by now
            raise AssertionError("a request with max_tokens has a token bound")
        return request, bound


def _charge(usage: Usage, hold: int) -> int:
    """The tokens an answered call is counted for.

    What it reported, when the report is complete. A report that leaves a count out (or
    is absent) is only a floor: the call is charged its whole hold, or the floor when
    that is higher, so a provider that under-reports cannot slip past its daily quota.
    """
    return usage.total if usage.complete else max(hold, usage.total)


def _settle_breaker(breaker: CircuitBreaker, permit: Permit, error: ProviderError) -> Outcome:
    """Tell the breaker what a failed call means, and name the outcome."""
    if isinstance(error, ProviderRateLimitedError):
        breaker.trip(permit, error.retry_after)
        return "rate_limited"
    if isinstance(error, ProviderRejectedError):
        breaker.release(permit)  # the provider is up: it refused this request
        return "rejected"
    breaker.failure(permit)
    return "bad_response" if isinstance(error, ProviderResponseError) else "unavailable"
