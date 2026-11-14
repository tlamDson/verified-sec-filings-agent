"""A1 text and risk-diff outcomes: a cited non-answer is not a successful answer.

A text check (search_filings) needs a cited sentence from a passage of the asked company; a
risk-diff check needs a cited sentence naming a change of the compared filings. A system
without diff_risk_factors (RAG) must cite both filings it compared, the oracle naming them.
Passages, diffs and every answer text are simulated (they stand in for filing text and
what a model writes).
"""

import datetime as dt
import json
from typing import Any

from faithfulness_kit import (
    SIM_ACCESSION,
    SIM_PREVIOUS_ACCESSION,
    passage_citation,
    risk_diff_evidence,
    search_evidence,
)

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
DIFF_CALL = risk_diff_evidence("SIMULATED: We depend on a single supplier for casings.")


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


def test_a_cited_answer_from_the_companys_passage_passes() -> None:
    text = f"SIMULATED: SIM Widgets depends on a single casing supplier [{passage_citation(0)}]."
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == []
    assert kinds(TEXT, transcript(text, (PASSAGES,), offered=RAG_TOOLS)) == []


def test_a_cited_non_answer_fails_text_for_the_agent_and_rag() -> None:
    text = (
        "SIMULATED: The provided passages do not contain information about supply risk. "
        f"They describe widget casings [{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == ["non_answer"]
    assert kinds(TEXT, transcript(text, (PASSAGES,), offered=RAG_TOOLS)) == ["non_answer"]


def test_the_company_itself_not_described_is_a_non_answer() -> None:
    text = (
        "SIMULATED: SIM Widgets does not describe supply risk specifically. "
        f"It depends on a single supplier [{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (PASSAGES,), offered=RAG_TOOLS)) == ["non_answer"]


def test_the_cited_passage_must_be_of_the_asked_company() -> None:
    other = moved(PASSAGES, 0, citation="8888888888-25-000001/mdna/0")
    other = moved(other, 0, accession="8888888888-25-000001")
    result: dict[str, Any] = json.loads(other.result)
    result["passages"][0]["company"]["ticker"] = "OTHR"
    other = other.model_copy(update={"result": json.dumps(result)})
    text = "SIMULATED: A single supplier makes the casings [8888888888-25-000001/mdna/0]."
    assert kinds(TEXT, transcript(text, (other,))) == ["outcome"]


def test_the_agent_names_a_change_of_the_diff_it_called() -> None:
    text = f"SIMULATED: SIM Widgets added a risk factor on supplier dependence [{SIM_ACCESSION}]."
    assert kinds(RISK, transcript(text, (DIFF_CALL,))) == []


def test_a_cited_non_answer_fails_the_risk_diff() -> None:
    text = f"SIMULATED: The filing does not contain a list of changes [{SIM_ACCESSION}]."
    assert kinds(RISK, transcript(text, (DIFF_CALL,))) == ["outcome", "non_answer"]


def test_a_cited_sentence_naming_no_change_fails_the_risk_diff() -> None:
    text = f"SIMULATED: SIM Widgets depends on a single supplier [{SIM_ACCESSION}]."
    assert kinds(RISK, transcript(text, (DIFF_CALL,))) == ["outcome"]


ORACLE = (DIFF_CALL.model_copy(update={"call_id": "oracle-0"}),)
BOTH_FILINGS = moved(
    PASSAGES,
    1,
    citation=f"{SIM_PREVIOUS_ACCESSION}/risk_factors/1",
    accession=SIM_PREVIOUS_ACCESSION,
)


def test_rag_passes_a_risk_diff_by_citing_both_compared_filings() -> None:
    text = (
        "SIMULATED: SIM Widgets added a risk factor on supplier dependence "
        f"[{passage_citation(0)}], which its earlier 10-K did not name "
        f"[{SIM_PREVIOUS_ACCESSION}/risk_factors/1]."
    )
    rag = transcript(text, (BOTH_FILINGS,), offered=RAG_TOOLS, oracle=ORACLE)
    assert kinds(RISK, rag) == []


def test_rag_citing_only_the_latest_filing_did_not_compare() -> None:
    text = f"SIMULATED: SIM Widgets added a risk factor on suppliers [{passage_citation(0)}]."
    rag = transcript(text, (BOTH_FILINGS,), offered=RAG_TOOLS, oracle=ORACLE)
    assert kinds(RISK, rag) == ["outcome"]


def test_rag_citing_any_passage_no_longer_passes_a_risk_diff() -> None:
    """Before: a check of a tool RAG lacks, without a figure, was left to `cite` alone."""
    text = f"SIMULATED: SIM Widgets relies on one casing supplier [{passage_citation(0)}]."
    rag = transcript(text, (PASSAGES,), offered=RAG_TOOLS, oracle=ORACLE)
    assert kinds(RISK, rag) == ["outcome"]


def test_without_the_oracle_rag_risk_diff_cannot_be_judged() -> None:
    text = f"SIMULATED: SIM Widgets added a risk factor on suppliers [{passage_citation(0)}]."
    assert kinds(RISK, transcript(text, (BOTH_FILINGS,), offered=RAG_TOOLS)) == ["oracle"]


def test_a_not_reported_answer_is_not_a_non_answer() -> None:
    """E12: saying a figure is not reported is the right answer, not a text outcome."""
    not_reported = TEXT.model_copy(
        update={
            "category": "not_reported",
            "tools": (ToolCheck(tool="get_fact", match={"status": "not_reported"}),),
            "cite": False,
            "says": (r"not reported",),
        }
    )
    text = "SIMULATED: The filings do not contain it: it is not reported."
    assert kinds(not_reported, transcript(text, (), offered=RAG_TOOLS)) == []
