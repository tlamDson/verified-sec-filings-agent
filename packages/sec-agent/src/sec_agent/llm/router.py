"""LLMRouter: the one way the agent calls a model.

Providers are tried in the order given. For each: the circuit breaker must allow a call,
then the quota must have room; a provider that fails is noted and the next one is tried.
When none answers, `AllProvidersFailedError` carries what each one did, and the agent
falls back to its degraded answer.
"""

import datetime as dt
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sec_agent.llm.attempts import Attempt, Outcome
from sec_agent.llm.breaker import BreakerConfig, BreakerState, CircuitBreaker
from sec_agent.llm.errors import (
    AllProvidersFailedError,
    LLMConfigError,
    ProviderError,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderResponseError,
)
from sec_agent.llm.messages import ChatRequest, Completion
from sec_agent.llm.provider import Provider
from sec_agent.llm.quota import QuotaStore

__all__ = ["Attempt", "LLMRouter", "RouterResult"]


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
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        if not providers:
            raise LLMConfigError("no provider is configured")
        config = breaker or BreakerConfig()
        self._providers = tuple(providers)
        self._quota = quota
        self._now = now
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
        if not breaker.acquire():
            attempts.append(Attempt(name, "breaker_open", ""))
            return None
        try:
            if not self._quota.reserve(name, provider.limits, self._now()):
                breaker.release()
                attempts.append(Attempt(name, "quota_exhausted", ""))
                return None
            completion = provider.complete(request)
        except ProviderError as error:
            attempts.append(Attempt(name, _settle(breaker, error), str(error)))
            return None
        except BaseException:  # a bug or a cancel says nothing about the provider
            breaker.release()
            raise
        breaker.success()
        self._quota.add_tokens(name, completion.usage.total, self._now())
        attempts.append(Attempt(name, "ok", ""))
        return completion


def _settle(breaker: CircuitBreaker, error: ProviderError) -> Outcome:
    """Tell the breaker what a failed call means, and name the outcome."""
    if isinstance(error, ProviderRateLimitedError):
        breaker.trip(error.retry_after)
        return "rate_limited"
    if isinstance(error, ProviderRejectedError):
        breaker.release()  # the provider is up: it refused this request
        return "rejected"
    breaker.failure()
    return "bad_response" if isinstance(error, ProviderResponseError) else "unavailable"
