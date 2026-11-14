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
            "config": config.model_dump(mode="json"),
            "pins": dict(sorted(pins.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:FINGERPRINT_CHARS]
