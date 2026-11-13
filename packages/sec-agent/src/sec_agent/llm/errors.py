"""Why an LLM call failed. Messages never carry a key or a provider's response body."""

from sec_agent.llm.attempts import Attempt


class LLMError(Exception):
    """Base class for every LLM router error."""


class LLMConfigError(LLMError, ValueError):
    """The providers are misconfigured: bad `LLM_PROVIDERS`, or a key variable is unset."""


class ProviderError(LLMError):
    """One provider failed one call; the router tries the next provider."""


class ProviderUnavailableError(ProviderError):
    """Timeout, transport error or a 5xx: the provider is down or too slow."""


class ProviderRateLimitedError(ProviderError):
    """HTTP 429. `retry_after` is the wait in seconds the provider asked for, if any."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderRejectedError(ProviderError):
    """Another 4xx: the provider is up but refused this request (or the key)."""


class ProviderResponseError(ProviderError):
    """A 2xx whose body is not a chat completion."""


class AllProvidersFailedError(LLMError):
    """No provider answered. `attempts` says what each one did, in order."""

    def __init__(self, attempts: tuple[Attempt, ...]) -> None:
        self.attempts = attempts
        tried = "; ".join(_describe(a) for a in attempts)
        super().__init__(f"no LLM provider answered ({tried})")


def _describe(attempt: Attempt) -> str:
    detail = f" ({attempt.detail})" if attempt.detail else ""
    return f"{attempt.provider}: {attempt.outcome}{detail}"
