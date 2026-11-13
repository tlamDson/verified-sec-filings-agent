"""An upper bound on the tokens one call can use, known before the call is made.

The router holds this much of a provider's daily token quota while the call runs, so
calls in flight can never add up to more than the quota. No tokenizer is needed: a token
covers at least one byte of text, so the bytes sent bound the prompt's tokens, and the
output limit bounds the reply. The bound is loose (several bytes per token on ordinary
text); the unused part goes back as soon as the call reports what it used.
"""

import json

from sec_agent.llm.messages import ChatRequest

_FRAMING_TOKENS = 16
"""Allowance for the tokens a chat template adds around each message and tool."""


def token_bound(request: ChatRequest) -> int | None:
    """Prompt bytes, framing allowance and `max_tokens`; None when the output is unlimited.

    It holds as long as the provider honours `max_tokens`; a call that reports more is
    charged what it reports.
    """
    if request.max_tokens is None:
        return None
    messages, tools = list(request.messages), list(request.tools)
    sent = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False)
    prompt = len(sent.encode("utf-8", errors="surrogatepass"))
    framing = _FRAMING_TOKENS * (len(messages) + len(tools) + 1)
    return prompt + framing + request.max_tokens
