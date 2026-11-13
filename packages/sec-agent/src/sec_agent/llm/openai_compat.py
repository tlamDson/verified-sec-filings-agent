"""OpenAICompatProvider: one `POST {base_url}/chat/completions`, with every failure named.

The only code in the repository that calls a model. It serves llama.cpp's local server
and free hosted endpoints alike. No retry here: the router moves to the next provider.
Redirects are not followed, and error messages hold the status only, never the body
(a provider may echo the key back) and never the key.
"""

from types import TracebackType
from typing import Self

import httpx

from sec_agent.llm.errors import (
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from sec_agent.llm.messages import ChatRequest, Completion
from sec_agent.llm.openai_wire import parse_completion, request_body
from sec_agent.llm.provider import ProviderConfig
from sec_agent.llm.quota import QuotaLimits

_UNAVAILABLE = frozenset({408, 425})  # with every 5xx: worth another provider, and a breaker count


class OpenAICompatProvider:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._url = config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(config.timeout_seconds),
            headers=headers,
            follow_redirects=False,
        )

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def limits(self) -> QuotaLimits:
        return self._config.limits

    def complete(self, request: ChatRequest) -> Completion:
        name = self._config.name
        try:
            response = self._http.post(self._url, json=request_body(self._config.model, request))
        except httpx.TimeoutException as error:
            wait = self._config.timeout_seconds
            raise ProviderUnavailableError(f"{name} timed out after {wait:g} s") from error
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(f"{name}: {type(error).__name__}") from error
        status = response.status_code
        if status == 429:
            raise ProviderRateLimitedError(
                f"HTTP 429 from {name}", retry_after=_seconds(response.headers.get("retry-after"))
            )
        if status >= 500 or status in _UNAVAILABLE:
            raise ProviderUnavailableError(f"HTTP {status} from {name}")
        if status >= 400:
            raise ProviderRejectedError(f"HTTP {status} from {name}")
        if status != 200:
            raise ProviderResponseError(f"HTTP {status} from {name} is not a completion")
        try:
            payload: object = response.json()
        except ValueError as error:
            raise ProviderResponseError(f"{name} did not answer in JSON") from error
        return parse_completion(payload, model=self._config.model)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _seconds(retry_after: str | None) -> float | None:
    """A Retry-After given in seconds; None for a date or anything else."""
    text = (retry_after or "").strip()
    return float(text) if text.isascii() and text.isdigit() else None
