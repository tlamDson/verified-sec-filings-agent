"""b0 and b1 ask their chat model through the provider router; the model is simulated."""

import pytest
from agent_kit import router_of
from llm_fakes import ScriptedProvider, says

from sec_agent.eval.chat import RouterChatModel
from sec_agent.eval.numeric.baselines import Message
from sec_agent.llm.errors import AllProvidersFailedError, ProviderUnavailableError

PROMPT = [Message(role="system", content="rules"), Message(role="user", content="question")]


def test_the_reply_text_comes_back_and_the_request_is_deterministic() -> None:
    provider = ScriptedProvider("local", [says('SIMULATED {"answer": "not_found"}')])
    model = RouterChatModel(router_of(provider), name="local:qwen", max_tokens=512)
    assert model.name == "local:qwen@max_tokens=512", "the output limit is part of the cache key"
    assert model.complete(PROMPT) == 'SIMULATED {"answer": "not_found"}'
    [request] = provider.requests
    assert [dict(m) for m in request.messages] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "question"},
    ]
    assert (request.temperature, request.max_tokens, tuple(request.tools)) == (0.0, 512, ())


def test_a_reply_without_text_is_an_empty_answer() -> None:
    provider = ScriptedProvider("local", [{"role": "assistant", "content": None}])
    assert RouterChatModel(router_of(provider), name="m").complete(PROMPT) == ""


def test_no_provider_raises_so_the_run_stops_rather_than_caching_a_failure() -> None:
    provider = ScriptedProvider("local", [ProviderUnavailableError("503")])
    with pytest.raises(AllProvidersFailedError):
        RouterChatModel(router_of(provider), name="m").complete(PROMPT)
