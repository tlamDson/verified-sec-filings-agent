"""A simulated OpenAI-compatible model for load and chaos runs. It is not a model.

Under load the replicas must call something that answers like a provider without costing
anything or spending a free quota. This server does: the first call of a turn asks for one
fact with `get_fact` (so the load reaches the tools and the database), and a call that
already holds a tool result gets a fixed reply with no number in it. `PUT /admin/mode`
switches it to answer 429 with `Retry-After`, the provider-429 chaos case.
"""

import itertools
import json
import threading
from typing import Any, Literal, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["ok", "rate_limited"]
FAKE_ANSWER = "The figures shown above come from the filings. (Simulated model reply.)"
DEFAULT_TOOL_ARGUMENTS: dict[str, Any] = {
    "company": "AAPL",
    "concept": "revenue",
    "fiscal_year": 2024,
}
_TOOL = "get_fact"
_COMPLETION_TOKENS = 20


class ModeBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Mode
    retry_after_seconds: int = Field(default=60, ge=1, le=3600)


class FakeLLMState:
    """Mode and counters, shared by the server's worker threads."""

    def __init__(
        self,
        *,
        mode: Mode = "ok",
        retry_after_seconds: int = 60,
        tool_arguments: dict[str, Any] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._mode: Mode = mode
        self._retry_after_seconds = retry_after_seconds
        self.tool_arguments: dict[str, Any] = dict(tool_arguments or DEFAULT_TOOL_ARGUMENTS)
        self._served = 0
        self._rate_limited = 0
        self._ids = itertools.count(1)

    def set_mode(self, body: ModeBody) -> None:
        with self._lock:
            self._mode = body.mode
            self._retry_after_seconds = body.retry_after_seconds

    def admit(self) -> tuple[bool, int, int]:
        """(served, call number, retry-after seconds) for one call, counted under the lock."""
        with self._lock:
            number = next(self._ids)
            if self._mode == "rate_limited":
                self._rate_limited += 1
                return False, number, self._retry_after_seconds
            self._served += 1
            return True, number, 0

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "mode": self._mode,
                "served": self._served,
                "rate_limited": self._rate_limited,
            }


def create_fake_llm(state: FakeLLMState | None = None, *, model: str = "fake-llm-sim") -> FastAPI:
    shared = state or FakeLLMState()
    app = FastAPI(title="fake LLM (simulated)", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/v1/chat/completions")
    async def complete(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        body: Any = await request.json()
        served, number, retry_after = shared.admit()
        if not served:
            return JSONResponse(
                {"error": {"message": "rate limited (simulated)", "type": "rate_limit"}},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        request_body = cast(dict[str, Any], body) if isinstance(body, dict) else {}
        return JSONResponse(_reply(request_body, number, model, shared.tool_arguments))

    @app.put("/admin/mode")
    def set_mode(body: ModeBody) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        shared.set_mode(body)
        return shared.snapshot()

    @app.get("/admin/state")
    def get_state() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return shared.snapshot()

    return app


def _reply(
    body: dict[str, Any], number: int, model: str, tool_arguments: dict[str, Any]
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = body.get("messages") or []
    message: dict[str, Any]
    if _offers(body, _TOOL) and not any(m.get("role") == "tool" for m in messages):
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_sim_{number}",
                    "type": "function",
                    "function": {"name": _TOOL, "arguments": json.dumps(tool_arguments)},
                }
            ],
        }
        finish = "tool_calls"
    else:
        message = {"role": "assistant", "content": FAKE_ANSWER}
        finish = "stop"
    prompt_tokens = max(1, len(json.dumps(messages)) // 4)
    return {
        "id": f"chatcmpl-sim-{number}",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "finish_reason": finish, "message": message}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": _COMPLETION_TOKENS,
            "total_tokens": prompt_tokens + _COMPLETION_TOKENS,
        },
    }


def _offers(body: dict[str, Any], name: str) -> bool:
    tools: list[dict[str, Any]] = body.get("tools") or []
    return any(tool.get("function", {}).get("name") == name for tool in tools)
