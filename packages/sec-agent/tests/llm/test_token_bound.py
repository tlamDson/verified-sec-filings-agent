"""token_bound: a number of tokens one call cannot exceed, known before the call is made."""

import json

from sec_agent.llm.messages import ChatRequest, Message, ToolSchema
from sec_agent.llm.token_bound import token_bound

QUESTION: list[Message] = [{"role": "user", "content": "question"}]
TOOL: ToolSchema = {
    "type": "function",
    "function": {"name": "get_fact", "description": "d" * 300, "parameters": {"type": "object"}},
}


def _bound(request: ChatRequest) -> int:
    bound = token_bound(request)
    assert bound is not None
    return bound


def test_the_bound_is_the_prompt_in_bytes_plus_the_output_limit() -> None:
    """A token is at least one byte of text, so the bytes sent bound the prompt's tokens."""
    small = _bound(ChatRequest(messages=QUESTION, max_tokens=64))
    assert small >= len(json.dumps(QUESTION).encode()) + 64
    assert _bound(ChatRequest(messages=QUESTION, max_tokens=1064)) == small + 1000


def test_text_outside_ascii_counts_its_bytes_not_its_characters() -> None:
    text = "Biên lợi nhuận gộp của NVIDIA"
    bound = _bound(ChatRequest(messages=[{"role": "user", "content": text}], max_tokens=1))
    assert len(text.encode("utf-8")) > len(text)
    assert bound >= len(text.encode("utf-8")) + 1


def test_every_message_and_tool_sent_adds_to_the_bound() -> None:
    one = _bound(ChatRequest(messages=QUESTION, max_tokens=64))
    two = _bound(ChatRequest(messages=[*QUESTION, *QUESTION], max_tokens=64))
    with_tool = _bound(ChatRequest(messages=QUESTION, tools=[TOOL], max_tokens=64))
    assert two > one + len("question")
    assert with_tool >= one + 300


def test_tool_calls_of_earlier_replies_are_counted() -> None:
    reply: Message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "get_fact", "arguments": "x" * 500},
            }
        ],
    }
    plain = _bound(ChatRequest(messages=QUESTION, max_tokens=64))
    assert _bound(ChatRequest(messages=[*QUESTION, reply], max_tokens=64)) >= plain + 500


def test_a_request_without_an_output_limit_has_no_bound() -> None:
    assert token_bound(ChatRequest(messages=QUESTION)) is None
