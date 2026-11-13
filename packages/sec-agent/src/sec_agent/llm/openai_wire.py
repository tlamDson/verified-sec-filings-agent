"""The OpenAI-compatible chat wire format: the request body, and the reply read back.

Only the fields the agent uses are read. Hidden reasoning (`reasoning_content`) and any
other extra field of a reply are dropped, so they never reach the conversation.
"""

from typing import Any, cast

from sec_agent.llm.errors import ProviderResponseError
from sec_agent.llm.messages import ChatRequest, Completion, Message, ToolCall, Usage


def request_body(model: str, request: ChatRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": list(request.messages),
        "temperature": request.temperature,
    }
    if request.tools:
        body["tools"] = list(request.tools)
        body["tool_choice"] = request.tool_choice
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    return body


def parse_completion(payload: object, *, model: str) -> Completion:
    """Read a `chat/completions` reply; `model` names it when the reply does not."""
    body = _object(payload, "the reply")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderResponseError("the reply has no choices")
    choice = _object(cast(list[object], choices)[0], "the first choice")
    finish = choice.get("finish_reason")
    named = body.get("model")
    return Completion(
        message=_message(_object(choice.get("message"), "the message")),
        finish_reason=finish if isinstance(finish, str) else "stop",
        usage=_usage(body.get("usage")),
        model=named if isinstance(named, str) and named else model,
    )


def _message(raw: dict[str, Any]) -> Message:
    if raw.get("role") != "assistant":
        raise ProviderResponseError("the reply is not an assistant message")
    content = raw.get("content")
    if content is not None and not isinstance(content, str):
        raise ProviderResponseError("the reply's content is not text")
    calls = _tool_calls(raw.get("tool_calls"))
    if not calls:
        if content is None:
            raise ProviderResponseError("the reply has neither text nor tool calls")
        return {"role": "assistant", "content": content}
    return {"role": "assistant", "content": content or None, "tool_calls": calls}


def _tool_calls(raw: object) -> list[ToolCall]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProviderResponseError("tool_calls is not a list")
    calls: list[ToolCall] = []
    for index, item in enumerate(cast(list[object], raw)):
        call = _object(item, "a tool call")
        function = _object(call.get("function"), "a tool call's function")
        name, arguments, call_id = function.get("name"), function.get("arguments"), call.get("id")
        if not isinstance(name, str) or not name or not isinstance(arguments, str):
            raise ProviderResponseError("a tool call needs a name and its arguments as text")
        calls.append(
            {
                "id": call_id if isinstance(call_id, str) and call_id else f"call_{index}",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        )
    return calls


def _usage(raw: object) -> Usage:
    """Token counts as the provider reports them; zero when it reports none."""
    usage = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    return Usage(
        prompt_tokens=_count(usage.get("prompt_tokens")),
        completion_tokens=_count(usage.get("completion_tokens")),
    )


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _object(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderResponseError(f"{what} is not a JSON object")
    return cast(dict[str, Any], value)
