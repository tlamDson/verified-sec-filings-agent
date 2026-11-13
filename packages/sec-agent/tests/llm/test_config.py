"""Providers from the environment: order, limits, and keys that never sit in the repository."""

import json

import httpx
import pytest
from llm_fakes import fixture_json

from sec_agent.llm.config import DEFAULT_PROVIDERS, build_providers, providers_from_env
from sec_agent.llm.errors import LLMConfigError
from sec_agent.llm.messages import ChatRequest
from sec_agent.llm.quota import QuotaLimits

TWO = json.dumps(
    [
        {
            "name": "hosted",
            "base_url": "https://llm.example.com/v1",
            "model": "sim-model-a",
            "api_key_env": "SIM_LLM_KEY",
            "timeout_seconds": 20,
            "limits": {"requests_per_minute": 30, "requests_per_day": 1000},
        },
        {"name": "local", "base_url": "http://127.0.0.1:8080/v1", "model": "sim-model-b"},
    ]
)


def test_without_configuration_the_only_provider_is_the_local_server() -> None:
    providers = providers_from_env({})
    assert providers == DEFAULT_PROVIDERS
    (local,) = providers
    assert local.name == "local"
    assert local.base_url.startswith("http://127.0.0.1:")
    assert local.api_key_env is None
    assert local.limits == QuotaLimits()


def test_providers_keep_the_order_they_are_listed_in() -> None:
    hosted, local = providers_from_env({"LLM_PROVIDERS": TWO})
    assert (hosted.name, local.name) == ("hosted", "local")
    assert hosted.timeout_seconds == 20
    assert hosted.limits == QuotaLimits(requests_per_minute=30, requests_per_day=1000)
    assert hosted.api_key_env == "SIM_LLM_KEY"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "LLM_PROVIDERS"),
        ("{}", "list"),
        ("[]", "no provider"),
        ('[{"name": "a", "base_url": "http://x/v1"}]', "model"),
        ('[{"name": "a", "base_url": "http://x/v1", "model": "m", "api_key": "sk"}]', "api_key"),
        ('[{"name": "a", "base_url": "ftp://x/v1", "model": "m"}]', "base_url"),
        ('[{"name": "a b", "base_url": "http://x/v1", "model": "m"}]', "name"),
        (
            '[{"name": "a", "base_url": "http://x/v1", "model": "m"},'
            ' {"name": "a", "base_url": "http://y/v1", "model": "m"}]',
            "twice",
        ),
    ],
)
def test_a_wrong_configuration_is_refused(text: str, message: str) -> None:
    with pytest.raises(LLMConfigError, match=message):
        providers_from_env({"LLM_PROVIDERS": text})


def test_a_key_is_read_from_the_variable_the_configuration_names() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture_json("chat_answer.sim.json"))

    environ = {"LLM_PROVIDERS": TWO, "SIM_LLM_KEY": "sk-sim-not-a-real-key"}
    hosted, local = build_providers(
        providers_from_env(environ), environ, transport=httpx.MockTransport(handler)
    )
    request = ChatRequest(messages=[{"role": "user", "content": "q"}])
    hosted.complete(request)
    local.complete(request)
    assert seen[0].headers["authorization"] == "Bearer sk-sim-not-a-real-key"
    assert "authorization" not in seen[1].headers
    assert (hosted.name, local.name) == ("hosted", "local")


def test_a_missing_key_names_its_variable() -> None:
    with pytest.raises(LLMConfigError, match="SIM_LLM_KEY"):
        build_providers(providers_from_env({"LLM_PROVIDERS": TWO}), {})
