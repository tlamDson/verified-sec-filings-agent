"""The per-role thinking setting: sent as `chat_template_kwargs.enable_thinking` when set,
and absent (the server's own default) when not. A fake server (`httpx.MockTransport`)
stands in for llama.cpp."""

import json
from typing import Any

import httpx
import pytest
from llm_fakes import fixture_json

from sec_agent.llm.config import build_providers, model_label, providers_from_env
from sec_agent.llm.errors import LLMConfigError
from sec_agent.llm.messages import ChatRequest, LLMRole
from sec_agent.llm.openai_compat import OpenAICompatProvider
from sec_agent.llm.openai_wire import request_body
from sec_agent.llm.provider import ProviderConfig
from sec_agent.llm.thinking import ThinkingSettings

MESSAGES: list[Any] = [{"role": "user", "content": "question"}]
ROLES: tuple[LLMRole, ...] = ("answer", "tool_choice", "judge", "guardrail")


def _config(**thinking: bool) -> ProviderConfig:
    return ProviderConfig(
        name="local",
        base_url="http://127.0.0.1:8081/v1",
        model="local",
        thinking=ThinkingSettings(**thinking),
    )


def _sent(config: ProviderConfig, role: LLMRole) -> dict[str, Any]:
    """The JSON body the fake server receives for a request of `role`."""
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=fixture_json("chat_answer.sim.json"))

    provider = OpenAICompatProvider(config, transport=httpx.MockTransport(handler))
    provider.complete(ChatRequest(messages=MESSAGES, role=role))
    (body,) = seen
    return body


def test_a_request_is_for_the_answer_unless_it_says_otherwise() -> None:
    assert ChatRequest(messages=MESSAGES).role == "answer"


def test_by_default_no_role_sends_a_template_setting() -> None:
    for role in ROLES:
        assert "chat_template_kwargs" not in _sent(_config(), role)


def test_a_role_set_off_sends_enable_thinking_false_and_the_others_send_nothing() -> None:
    config = _config(answer=False)
    assert _sent(config, "answer")["chat_template_kwargs"] == {"enable_thinking": False}
    for role in ("tool_choice", "judge", "guardrail"):
        assert "chat_template_kwargs" not in _sent(config, role)


def test_a_role_set_on_sends_enable_thinking_true() -> None:
    body = _sent(_config(judge=True), "judge")
    assert body["chat_template_kwargs"] == {"enable_thinking": True}


def test_each_role_has_its_own_setting() -> None:
    config = _config(answer=False, tool_choice=True, judge=False, guardrail=True)
    flags = {r: _sent(config, r)["chat_template_kwargs"]["enable_thinking"] for r in ROLES}
    assert flags == {"answer": False, "tool_choice": True, "judge": False, "guardrail": True}


def test_the_rest_of_the_body_is_the_same_with_or_without_the_setting() -> None:
    request = ChatRequest(messages=MESSAGES, max_tokens=64)
    plain = request_body("local", request, ThinkingSettings())
    off = request_body("local", request, ThinkingSettings(answer=False))
    assert {k: v for k, v in off.items() if k != "chat_template_kwargs"} == plain


def test_the_setting_is_read_from_the_provider_list() -> None:
    text = json.dumps(
        [
            {
                "name": "local",
                "base_url": "http://127.0.0.1:8081/v1",
                "model": "local",
                "thinking": {"answer": False, "tool_choice": False},
            }
        ]
    )
    (config,) = providers_from_env({"LLM_PROVIDERS": text})
    assert config.thinking == ThinkingSettings(answer=False, tool_choice=False)
    (provider,) = build_providers((config,), {})
    assert isinstance(provider, OpenAICompatProvider)


@pytest.mark.parametrize(
    "thinking", [{"summary": False}, {"answer": "off"}, {"answer": 0}, {"answer": None, "x": 1}]
)
def test_an_unknown_role_or_a_value_that_is_not_true_or_false_is_refused(thinking: object) -> None:
    text = json.dumps(
        [{"name": "local", "base_url": "http://x/v1", "model": "m", "thinking": thinking}]
    )
    with pytest.raises(LLMConfigError, match=r"LLM_PROVIDERS\[0\]: thinking"):
        providers_from_env({"LLM_PROVIDERS": text})


def test_the_model_label_is_unchanged_without_a_setting() -> None:
    assert model_label((_config(), _config())) == "local:local+local:local"


def test_the_model_label_names_the_setting_so_a_cached_answer_is_never_reused() -> None:
    label = model_label((_config(answer=False, tool_choice=True),))
    assert label == "local:local[thinking answer=off tool_choice=on]"
    assert label != model_label((_config(),))
    assert label != model_label((_config(answer=False),))
