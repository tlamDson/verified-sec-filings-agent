"""OpenAICompatProvider: one HTTP call, and each way it can fail named for the router.

No network: `httpx.MockTransport` answers with the simulated fixtures.
"""

import json
from collections.abc import Callable

import httpx
import pytest
from llm_fakes import fixture_json

from sec_agent.llm.errors import (
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from sec_agent.llm.messages import ChatRequest
from sec_agent.llm.openai_compat import OpenAICompatProvider
from sec_agent.llm.provider import ProviderConfig
from sec_agent.llm.quota import QuotaLimits

CONFIG = ProviderConfig(
    name="sim-a",
    base_url="https://llm.example.com/v1/",
    model="sim-model-a",
    timeout_seconds=5,
    limits=QuotaLimits(requests_per_day=100),
)
REQUEST = ChatRequest(messages=[{"role": "user", "content": "question"}])
SECRET = "sk-sim-not-a-real-key"

Handler = Callable[[httpx.Request], httpx.Response]


def _provider(handler: Handler, *, api_key: str | None = None) -> OpenAICompatProvider:
    return OpenAICompatProvider(CONFIG, api_key=api_key, transport=httpx.MockTransport(handler))


def _status(code: int, **headers: str) -> Handler:
    return lambda request: httpx.Response(code, headers=headers, json={"error": {"message": "x"}})


def test_posts_the_chat_request_and_reads_the_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture_json("chat_answer.sim.json"))

    provider = _provider(handler)
    completion = provider.complete(REQUEST)
    assert completion.message["content"] == (
        "SIMULATED reply: the figure is in the tool result above."
    )
    assert (provider.name, provider.limits) == ("sim-a", QuotaLimits(requests_per_day=100))
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://llm.example.com/v1/chat/completions"
    assert json.loads(request.content) == {
        "model": "sim-model-a",
        "messages": [{"role": "user", "content": "question"}],
        "temperature": 0.0,
    }
    assert "authorization" not in request.headers


def test_a_key_is_sent_as_a_bearer_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture_json("chat_answer.sim.json"))

    _provider(handler, api_key=SECRET).complete(REQUEST)
    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"


def test_429_is_rate_limited_with_the_wait_the_provider_asks_for() -> None:
    with pytest.raises(ProviderRateLimitedError) as caught:
        _provider(_status(429, **{"Retry-After": "7"})).complete(REQUEST)
    assert caught.value.retry_after == 7.0


def test_429_without_a_usable_retry_after_has_no_wait() -> None:
    with pytest.raises(ProviderRateLimitedError) as caught:
        _provider(_status(429, **{"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})).complete(
            REQUEST
        )
    assert caught.value.retry_after is None


@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_server_errors_are_unavailable(code: int) -> None:
    with pytest.raises(ProviderUnavailableError, match=str(code)):
        _provider(_status(code)).complete(REQUEST)


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_other_client_errors_are_rejections(code: int) -> None:
    with pytest.raises(ProviderRejectedError, match=str(code)):
        _provider(_status(code)).complete(REQUEST)


def test_a_timeout_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderUnavailableError, match="timed out"):
        _provider(handler).complete(REQUEST)


def test_a_refused_connection_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailableError):
        _provider(handler).complete(REQUEST)


def test_a_reply_that_is_not_json_is_a_bad_response() -> None:
    with pytest.raises(ProviderResponseError):
        _provider(lambda request: httpx.Response(200, text="<html>gateway</html>")).complete(
            REQUEST
        )


def test_errors_never_carry_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": f"bad key {SECRET}"}})

    with pytest.raises(ProviderRejectedError) as caught:
        _provider(handler, api_key=SECRET).complete(REQUEST)
    assert SECRET not in str(caught.value)


def test_the_timeout_comes_from_the_configuration() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture_json("chat_answer.sim.json"))

    _provider(handler).complete(REQUEST)
    assert seen[0].extensions["timeout"]["read"] == 5
