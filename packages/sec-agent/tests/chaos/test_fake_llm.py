"""The simulated OpenAI-compatible model used under load: no real model, no cost."""

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sec_agent.chaos.fake_llm import FAKE_ANSWER, FakeLLMState, create_fake_llm

GET_FACT = {
    "type": "function",
    "function": {"name": "get_fact", "description": "d", "parameters": {"type": "object"}},
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_fake_llm(FakeLLMState()))


def _ask(client: TestClient, messages: list[dict[str, Any]], tools: list[Any]) -> Any:
    body: dict[str, Any] = {"model": "fake", "messages": messages}
    if tools:
        body["tools"] = tools
    return client.post("/v1/chat/completions", json=body)


def test_first_call_with_tools_asks_for_a_fact(client: TestClient) -> None:
    response = _ask(client, [{"role": "user", "content": "Apple revenue?"}], [GET_FACT])
    assert response.status_code == 200
    choice = response.json()["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    call = choice["message"]["tool_calls"][0]
    assert call["function"]["name"] == "get_fact"
    assert '"company"' in call["function"]["arguments"]
    usage = response.json()["usage"]
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0


def test_after_a_tool_result_it_answers_without_any_number(client: TestClient) -> None:
    messages = [
        {"role": "user", "content": "Apple revenue?"},
        {"role": "tool", "tool_call_id": "c1", "content": "{}"},
    ]
    choice = _ask(client, messages, [GET_FACT]).json()["choices"][0]
    assert choice["finish_reason"] == "stop"
    assert choice["message"]["content"] == FAKE_ANSWER
    assert not re.search(r"\d", FAKE_ANSWER)  # numbers only ever come from tools
    assert "simulated" in FAKE_ANSWER


def test_without_tools_it_answers(client: TestClient) -> None:
    choice = _ask(client, [{"role": "user", "content": "hi"}], []).json()["choices"][0]
    assert choice["message"]["content"] == FAKE_ANSWER


def test_rate_limited_mode_returns_429_with_retry_after(client: TestClient) -> None:
    switched = client.put("/admin/mode", json={"mode": "rate_limited", "retry_after_seconds": 7})
    assert switched.status_code == 200
    response = _ask(client, [{"role": "user", "content": "hi"}], [])
    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    state = client.get("/admin/state").json()
    assert state == {"mode": "rate_limited", "served": 0, "rate_limited": 1}


def test_switching_back_to_ok_serves_again(client: TestClient) -> None:
    client.put("/admin/mode", json={"mode": "rate_limited"})
    client.put("/admin/mode", json={"mode": "ok"})
    assert _ask(client, [{"role": "user", "content": "hi"}], []).status_code == 200
    assert client.get("/admin/state").json()["served"] == 1


def test_unknown_mode_is_refused(client: TestClient) -> None:
    assert client.put("/admin/mode", json={"mode": "on_fire"}).status_code == 422


def test_tool_arguments_are_configurable() -> None:
    state = FakeLLMState(tool_arguments={"company": "NVDA", "concept": "revenue"})
    client = TestClient(create_fake_llm(state))
    call = _ask(client, [{"role": "user", "content": "q"}], [GET_FACT]).json()["choices"][0]
    assert "NVDA" in call["message"]["tool_calls"][0]["function"]["arguments"]
