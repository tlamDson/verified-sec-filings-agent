"""Provider 429 under the real router: fail over in order; all limited means no model."""

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from sec_agent.chaos.fake_llm import FAKE_ANSWER, FakeLLMState, create_fake_llm
from sec_agent.llm.config import build_providers
from sec_agent.llm.errors import AllProvidersFailedError
from sec_agent.llm.messages import ChatRequest, user
from sec_agent.llm.provider import ProviderConfig
from sec_agent.llm.quota import MemoryQuotaStore
from sec_agent.llm.router import LLMRouter

CONFIGS = (
    ProviderConfig(name="a", base_url="http://llm-a/v1", model="fake"),
    ProviderConfig(name="b", base_url="http://llm-b/v1", model="fake"),
)


@pytest.fixture
def fakes() -> Iterator[dict[str, TestClient]]:
    clients = {
        "llm-a": TestClient(create_fake_llm(FakeLLMState())),
        "llm-b": TestClient(create_fake_llm(FakeLLMState())),
    }
    yield clients
    for client in clients.values():
        client.close()


def _router(fakes: dict[str, TestClient]) -> LLMRouter:
    def route(request: httpx.Request) -> httpx.Response:
        reply = fakes[request.url.host].request(
            request.method, request.url.path, content=request.content, headers=request.headers
        )
        return httpx.Response(reply.status_code, headers=reply.headers, content=reply.content)

    providers = build_providers(CONFIGS, {}, transport=httpx.MockTransport(route))
    return LLMRouter(providers, quota=MemoryQuotaStore())


def _ask(router: LLMRouter) -> str:
    return router.complete(ChatRequest(messages=[user("hello")])).provider


def test_first_provider_answers_when_all_are_up(fakes: dict[str, TestClient]) -> None:
    result = _router(fakes).complete(ChatRequest(messages=[user("hello")]))
    assert result.provider == "a"
    assert result.completion.message.get("content") == FAKE_ANSWER


def test_429_on_the_first_provider_fails_over_to_the_next(
    fakes: dict[str, TestClient],
) -> None:
    fakes["llm-a"].put("/admin/mode", json={"mode": "rate_limited", "retry_after_seconds": 30})
    router = _router(fakes)
    result = router.complete(ChatRequest(messages=[user("hello")]))
    assert result.provider == "b"
    assert [attempt.outcome for attempt in result.attempts] == ["rate_limited", "ok"]
    assert router.breaker_state("a") == "open"
    assert _ask(router) == "b"  # the open breaker skips a without calling it
    assert fakes["llm-a"].get("/admin/state").json()["rate_limited"] == 1


def test_every_provider_limited_means_no_model_answers(fakes: dict[str, TestClient]) -> None:
    for client in fakes.values():
        client.put("/admin/mode", json={"mode": "rate_limited"})
    with pytest.raises(AllProvidersFailedError):
        _ask(_router(fakes))
