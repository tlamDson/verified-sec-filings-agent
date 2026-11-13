"""The OpenAI-compatible wire format: the request body sent, and the reply read back.

The response fixtures are simulated (see `fixtures/llm/README.md`).
"""

import pytest
from llm_fakes import fixture_json

from sec_agent.llm.errors import ProviderResponseError
from sec_agent.llm.messages import ChatRequest, Message, ToolSchema, Usage
from sec_agent.llm.openai_wire import parse_completion, request_body

MESSAGES: list[Message] = [
    {"role": "system", "content": "rules"},
    {"role": "user", "content": "question"},
]
TOOL: ToolSchema = {
    "type": "function",
    "function": {"name": "get_fact", "description": "d", "parameters": {"type": "object"}},
}


def test_body_without_tools_has_no_tool_fields() -> None:
    body = request_body("sim-model-a", ChatRequest(messages=MESSAGES))
    assert body == {"model": "sim-model-a", "messages": MESSAGES, "temperature": 0.0}


def test_body_with_tools_names_the_tool_choice_and_the_output_limit() -> None:
    request = ChatRequest(messages=MESSAGES, tools=[TOOL], tool_choice="none", max_tokens=512)
    body = request_body("sim-model-a", request)
    assert body["tools"] == [TOOL]
    assert body["tool_choice"] == "none"
    assert body["max_tokens"] == 512


def test_a_text_reply_is_read_with_its_usage() -> None:
    completion = parse_completion(fixture_json("chat_answer.sim.json"), model="configured")
    assert completion.message == {
        "role": "assistant",
        "content": "SIMULATED reply: the figure is in the tool result above.",
    }
    assert completion.finish_reason == "stop"
    assert completion.usage == Usage(prompt_tokens=120, completion_tokens=14)
    assert completion.usage.total == 134
    assert completion.model == "sim-model-a"


def test_a_tool_call_reply_keeps_the_calls_exactly() -> None:
    completion = parse_completion(fixture_json("chat_tool_call.sim.json"), model="configured")
    assert completion.message == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_sim_1",
                "type": "function",
                "function": {
                    "name": "get_fact",
                    "arguments": '{"company": "AAPL", "concept": "revenue", "fiscal_year": 2024}',
                },
            }
        ],
    }
    assert completion.finish_reason == "tool_calls"


def test_hidden_reasoning_is_dropped_and_missing_ids_and_usage_are_filled() -> None:
    completion = parse_completion(fixture_json("chat_reasoning.sim.json"), model="configured")
    message = completion.message
    assert set(message) == {"role", "content", "tool_calls"}
    assert message["content"] is None, "empty text beside tool calls is no text"
    assert [c["id"] for c in message.get("tool_calls", [])] == ["call_0", "call_1"]
    assert completion.usage == Usage(prompt_tokens=0, completion_tokens=0)
    assert completion.model == "sim-model-b"


def test_the_configured_model_names_a_reply_that_names_none() -> None:
    payload = fixture_json("chat_answer.sim.json")
    del payload["model"]
    assert parse_completion(payload, model="configured").model == "configured"


@pytest.mark.parametrize(
    "broken",
    [
        "not an object",
        {},
        {"choices": []},
        {"choices": [{"message": {"role": "user", "content": "x"}}]},
        {"choices": [{"message": {"role": "assistant", "content": 7}}]},
        {"choices": [{"message": {"role": "assistant", "content": None}}]},
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {"id": "c", "type": "function", "function": {"name": "get_fact"}}
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c",
                                "type": "function",
                                "function": {"name": "get_fact", "arguments": {"a": 1}},
                            }
                        ],
                    }
                }
            ]
        },
    ],
)
def test_a_reply_in_another_shape_is_refused(broken: object) -> None:
    with pytest.raises(ProviderResponseError):
        parse_completion(broken, model="configured")
