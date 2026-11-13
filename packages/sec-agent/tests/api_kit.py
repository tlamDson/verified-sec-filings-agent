"""Helpers the API tests share. Pytest puts this directory on sys.path (`pythonpath`).

The API runs in process (FastAPI's test client, no socket). The model is always a
`ScriptedProvider` (simulated: the test writes every reply); the numeric tools read the
recorded Apple and NVIDIA companyfacts fixtures. Every user here is made up for a test:
`REAL` only carries the cohort label `real`, it is no real person.
"""

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any

import httpx
from agent_kit import agent_of
from fastapi.testclient import TestClient
from llm_fakes import T0, ScriptedProvider

from sec_agent.agent.tool_runner import ToolOutput, ToolRunner
from sec_agent.api.app import ApiDeps, TurnAgent, create_app
from sec_agent.api.config import ApiConfig
from sec_agent.api.identity import Identity, sign_token
from sec_agent.api.store import ApiStore, MemoryApiStore
from sec_agent.llm.messages import ToolSchema
from sec_agent.tools.context import FactsContext

SECRET = "sim-shared-secret-0123456789abcdef0123456789"
NOW = T0
"""2026-11-13 09:30:15 UTC: the API's clock in every test."""
TODAY = NOW.date()
REAL = Identity(user_id="github:42", cohort="real")
OTHER = Identity(user_id="github:77", cohort="real")
SIM = Identity(user_id="sim:sim-07@example.com", cohort="simulated")
THREAD = "thread-0001"


@dataclass(frozen=True)
class Api:
    client: TestClient
    store: ApiStore

    def chat(
        self,
        question: str,
        *,
        user: Identity = REAL,
        thread_id: str = THREAD,
        asked_on: str | None = None,
    ) -> httpx.Response:
        body: dict[str, Any] = {"thread_id": thread_id, "question": question}
        if asked_on is not None:
            body["asked_on"] = asked_on
        return self.client.post("/v1/chat", json=body, headers=auth(user))


def api_of(
    facts: FactsContext,
    *providers: ScriptedProvider,
    store: ApiStore | None = None,
    daily_questions: int = 20,
    agent: TurnAgent | None = None,
) -> Api:
    kept = store or MemoryApiStore()
    deps = ApiDeps(
        agent=agent or agent_of(facts, *providers),
        tools=ToolRunner(facts),
        companies=facts.companies,
        store=kept,
        config=ApiConfig(auth_secret=SECRET, daily_questions=daily_questions),
        now=lambda: NOW,
    )
    return Api(client=TestClient(create_app(deps)), store=kept)


def auth(user: Identity, *, now: dt.datetime = NOW) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(user, SECRET, now=now)}"}


def events(response: httpx.Response) -> list[tuple[str, Any]]:
    """The (event, data) pairs of a server-sent event stream."""
    found: list[tuple[str, Any]] = []
    for block in response.text.split("\n\n"):
        if not block.strip():
            continue
        name, data = block.split("\n", 1)
        assert name.startswith("event: "), block
        assert data.startswith("data: "), block
        found.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return found


def event(response: httpx.Response, name: str) -> Any:
    """The data of the one event called `name`."""
    (data,) = [d for n, d in events(response) if n == name]
    return data


class RecordingTools:
    """The real numeric tools, plus a simulated `search_filings`; every call is recorded."""

    def __init__(self, facts: FactsContext, *, search_result: str | None = None) -> None:
        self._real = ToolRunner(facts)
        self._search_result = search_result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def names(self) -> tuple[str, ...]:
        extra = () if self._search_result is None else ("search_filings",)
        return (*self._real.names, *extra)

    def schemas(self) -> list[ToolSchema]:
        return self._real.schemas()

    def run(self, name: str, arguments: str) -> ToolOutput:
        self.calls.append((name, json.loads(arguments)))
        if name == "search_filings" and self._search_result is not None:
            return ToolOutput(True, self._search_result)
        return self._real.run(name, arguments)
