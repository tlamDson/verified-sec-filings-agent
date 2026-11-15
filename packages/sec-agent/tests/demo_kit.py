"""Small scenario and transcript builders for the demo site tests."""

import json
from typing import Any

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.scenarios import Scenario, Transcript

ACC = "0000093410-25-000009"
KEY = f"{ACC}/risk_factors/11"


def scenario(sid: str, category: str = "text", question: str = "What risks?") -> Scenario:
    return Scenario.model_validate(
        {
            "id": sid,
            "category": category,
            "split": "test",
            "turns": ["earlier turn", question],
            "cite": True,
        }
    )


def search(passages: list[dict[str, Any]]) -> Evidence:
    return Evidence(
        call_id="c1",
        name="search_filings",
        arguments=json.dumps({"query": "risk"}),
        result=json.dumps({"passages": passages}),
        ok=True,
    )


def fact(url: str = "https://www.sec.gov/x-index.htm") -> Evidence:
    result = {"status": "found", "fact": {"value": "56141000000", "filing_url": url}}
    return Evidence(
        call_id="c2",
        name="get_fact",
        arguments=json.dumps({"company": "COP", "concept": "revenue"}),
        result=json.dumps(result),
        ok=True,
    )


def transcript(
    sid: str,
    text: str,
    evidence: list[Evidence],
    *,
    status: str = "answered",
    system: str = "agent",
) -> Transcript:
    return Transcript.model_validate(
        {
            "scenario_id": sid,
            "system": system,
            "model": "agent:local:local",
            "scenario_sha256": "0" * 64,
            "text": text,
            "status": status,
            "evidence": [e.model_dump() for e in evidence],
            "asked_on": "2026-11-13",
            "answered_at": "2026-11-14T09:00:00Z",
        }
    )
