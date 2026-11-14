"""Shared setup of the A1 text-outcome tests: scenarios, simulated passages, transcripts."""

import datetime as dt
import json
from typing import Any

from faithfulness_kit import risk_diff_evidence, search_evidence

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.checks import check_scenario
from sec_agent.eval.agent.scenarios import Scenario, ToolCheck, Transcript

ASKED_ON = dt.date(2026, 11, 13)
NOW = dt.datetime(2026, 11, 13, 6, 0, tzinfo=dt.UTC)
RAG_TOOLS = ("search_filings",)
SEARCH = ToolCheck(tool="search_filings", match={"passages.*.company.ticker": "SIMW"})
DIFF = ToolCheck(
    tool="diff_risk_factors",
    match={"company.ticker": "SIMW", "status": "compared"},
    call={"company": "SIMW", "max_changes": 5},
)
TEXT = Scenario.model_validate(
    {
        "id": "a1-028",
        "category": "text",
        "split": "test",
        "companies": ("SIMW",),
        "turns": ("What does SIM Widgets say about supply risk?",),
        "tools": (SEARCH,),
        "cite": True,
    }
)
RISK = TEXT.model_copy(
    update={
        "id": "a1-034",
        "category": "risk_diff",
        "turns": ("Which risk factors did SIM Widgets add in its latest 10-K?",),
        "tools": (DIFF,),
    }
)
PASSAGES = search_evidence(
    "SIMULATED: We depend on a single supplier for our widget casings.",
    "SIMULATED: Our risk factors were revised to address supplier concentration.",
)
DIFF_CALL = risk_diff_evidence("SIMULATED: We depend on a single supplier for our widget casings.")


def moved(evidence: Evidence, index: int, **passage: str) -> Evidence:
    """`evidence` with passage `index` set to other fields (another company or filing)."""
    result: dict[str, Any] = json.loads(evidence.result)
    result["passages"][index].update(passage)
    return evidence.model_copy(update={"result": json.dumps(result)})


def transcript(
    text: str,
    evidence: tuple[Evidence, ...],
    *,
    offered: tuple[str, ...] | None = None,
    oracle: tuple[Evidence, ...] = (),
) -> Transcript:
    return Transcript.model_validate(
        {
            "scenario_id": "a1-028",
            "system": "agent" if offered is None else "rag",
            "model": "sim",
            "scenario_sha256": "0" * 64,
            "text": text,
            "status": "answered",
            "evidence": evidence,
            "asked_on": ASKED_ON,
            "answered_at": NOW,
            "offered_tools": offered,
            "oracle": oracle,
        }
    )


def kinds(scenario: Scenario, transcript_: Transcript) -> list[str]:
    return [f.kind for f in check_scenario(scenario, transcript_).failures]
