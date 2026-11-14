"""The chat model b0, b1 and the RAG-only A1 baseline ask: the provider router (s-09).

Requests are deterministic (temperature 0, no tools) and carry an output limit. When no
provider answers, `AllProvidersFailedError` propagates: the run stops with what it has
cached, rather than caching a failure as if it were an answer.
"""

from collections.abc import Sequence

from sec_agent.eval.numeric.baselines import Message
from sec_agent.llm.messages import ChatRequest
from sec_agent.llm.messages import Message as WireMessage
from sec_agent.llm.router import LLMRouter

DEFAULT_MAX_TOKENS = 1024


class RouterChatModel:
    def __init__(
        self, router: LLMRouter, *, name: str, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> None:
        """`name` identifies the model in answer records and cache keys, e.g. "local:qwen"."""
        self._router = router
        self._name = name
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return self._name

    def complete(self, messages: Sequence[Message]) -> str:
        wire: list[WireMessage] = [{"role": m.role, "content": m.content} for m in messages]
        result = self._router.complete(
            ChatRequest(messages=wire, max_tokens=self._max_tokens, temperature=0.0)
        )
        return result.completion.message.get("content") or ""
