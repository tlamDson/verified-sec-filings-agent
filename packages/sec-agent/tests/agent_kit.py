"""Helpers the agent tests share. Pytest puts this directory on sys.path (`pythonpath`).

The model is always a `ScriptedProvider` (simulated: the test writes every reply); the
numeric tools read the recorded Apple and NVIDIA companyfacts fixtures.
"""

import datetime as dt
import json
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from llm_fakes import Clock, ScriptedProvider
from opentelemetry.trace import Tracer

from sec_agent.agent.config import AgentConfig
from sec_agent.agent.service import Agent
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.llm.breaker import BreakerConfig
from sec_agent.llm.messages import ChatRequest, Message
from sec_agent.llm.quota import MemoryQuotaStore
from sec_agent.llm.router import LLMRouter
from sec_agent.tools.context import FactsContext, TextContext

ASKED_ON = dt.date(2026, 11, 13)
APPLE_REVENUE_FY2024 = "391035000000"


def router_of(*providers: ScriptedProvider, tracer: Tracer | None = None) -> LLMRouter:
    clock = Clock()
    return LLMRouter(
        providers,
        quota=MemoryQuotaStore(),
        breaker=BreakerConfig(failure_threshold=3, cooldown_seconds=30.0),
        clock=clock.monotonic,
        now=clock.now,
        tracer=tracer,
    )


def agent_of(
    facts: FactsContext,
    *providers: ScriptedProvider,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    config: AgentConfig | None = None,
    text: TextContext | None = None,
    tracer: Tracer | None = None,
) -> Agent:
    return Agent(
        router=router_of(*providers, tracer=tracer),
        tools=ToolRunner(facts, text),
        checkpointer=checkpointer or InMemorySaver(),
        config=config or AgentConfig(),
        tracer=tracer,
    )


def roles(request: ChatRequest) -> list[str]:
    return [m["role"] for m in request.messages]


def tool_messages(request: ChatRequest) -> list[Message]:
    return [m for m in request.messages if m["role"] == "tool"]


def loads(text: str | None) -> Any:
    assert text is not None
    return json.loads(text)
