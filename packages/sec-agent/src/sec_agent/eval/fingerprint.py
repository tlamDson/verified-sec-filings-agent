"""What an agent answer depends on besides the question: a short hash for cache keys.

A cached b2 answer or A1 transcript may be reused only when the agent that wrote it is the
same: its system prompt for the date asked, the tools it was offered (names, schemas), its
limits and checker settings (`AgentConfig`, including the output limit), and what its tools
are pinned to (facts version, text snapshot, reranker). Any change asks again.
"""

import datetime as dt
import hashlib
import json
from collections.abc import Mapping

from sec_agent.agent.config import AgentConfig
from sec_agent.agent.prompt import system_prompt
from sec_agent.agent.tool_runner import ToolRunner

FINGERPRINT_CHARS = 12


def agent_fingerprint(
    *, asked_on: dt.date, config: AgentConfig, tools: ToolRunner, pins: Mapping[str, str]
) -> str:
    payload = json.dumps(
        {
            "system_prompt": system_prompt(asked_on),
            "tools": tools.schemas(),
            "config": _stable_config(config),
            "pins": dict(sorted(pins.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:FINGERPRINT_CHARS]


def _stable_config(config: AgentConfig) -> dict[str, object]:
    """The config as JSON, with the per-config random canary replaced by a fixed mark: whether a
    canary is set changes answers, its random value does not, and it must not defeat the cache."""
    dumped: dict[str, object] = config.model_dump(mode="json")
    if config.guardrails is not None and config.guardrails.canary is not None:
        guardrails = config.guardrails.model_dump(mode="json")
        dumped["guardrails"] = {**guardrails, "canary": "<canary>"}
    return dumped
