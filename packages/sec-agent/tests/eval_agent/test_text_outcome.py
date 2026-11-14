"""A1 text and risk-diff outcomes: a cited non-answer is not a successful answer.

A text check (search_filings) needs a cited sentence that restates a passage of the asked
company; a risk-diff check needs a cited sentence naming and restating a change of the
compared filings. Citations alone, or a pointer ("see the 10-K"), state nothing. A system
without diff_risk_factors (RAG) must cite both filings it compared, the oracle naming them.
Passages, diffs and every answer text are simulated (they stand in for filing text and
what a model writes).
"""

import json
from typing import Any

from faithfulness_kit import (
    SIM_ACCESSION,
    SIM_PREVIOUS_ACCESSION,
    passage_citation,
    risk_diff_evidence,
)
from text_outcome_kit import (
    DIFF_CALL,
    PASSAGES,
    RAG_TOOLS,
    RISK,
    TEXT,
    kinds,
    moved,
    transcript,
)

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.scenarios import ToolCheck


def test_a_cited_answer_from_the_companys_passage_passes() -> None:
    text = f"SIMULATED: SIM Widgets depends on a single casing supplier [{passage_citation(0)}]."
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == []
    assert kinds(TEXT, transcript(text, (PASSAGES,), offered=RAG_TOOLS)) == []


def test_a_cited_non_answer_fails_text_for_the_agent_and_rag() -> None:
    text = (
        "SIMULATED: The provided passages do not contain information about supply risk. "
        f"They depend on a single supplier for widget casings [{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == ["non_answer"]
    assert kinds(TEXT, transcript(text, (PASSAGES,), offered=RAG_TOOLS)) == ["non_answer"]


def test_the_company_itself_not_described_is_a_non_answer() -> None:
    text = (
        "SIMULATED: SIM Widgets does not describe supply risk specifically. "
        f"It depends on a single supplier for its widget casings [{passage_citation(0)}]."
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
    text = (
        "SIMULATED: SIM Widgets added a risk factor: it depends on a single supplier for "
        f"widget casings [{SIM_ACCESSION}]."
    )
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
        "SIMULATED: SIM Widgets added a risk factor: it depends on a single supplier for "
        f"widget casings [{passage_citation(0)}], which its earlier 10-K did not name "
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


def test_a_citation_only_answer_fails_text_for_the_agent_and_rag() -> None:
    for text in (
        f"[{passage_citation(0)}]",
        f"SIMULATED: Sources: [{passage_citation(0)}] [{passage_citation(1)}].",
        f"SIMULATED: See the 10-K for details [{passage_citation(0)}].",
    ):
        assert kinds(TEXT, transcript(text, (PASSAGES,))) == ["outcome"], text
        assert kinds(TEXT, transcript(text, (PASSAGES,), offered=RAG_TOOLS)) == ["outcome"], text


def test_a_change_word_with_a_citation_is_not_a_risk_diff_answer() -> None:
    text = f"SIMULATED: Risk factors were added and changed [{SIM_ACCESSION}]."
    assert kinds(RISK, transcript(text, (DIFF_CALL,))) == ["outcome"]
    both = f"SIMULATED: Added [{passage_citation(0)}] [{SIM_PREVIOUS_ACCESSION}/risk_factors/1]."
    rag = transcript(both, (BOTH_FILINGS,), offered=RAG_TOOLS, oracle=ORACLE)
    assert kinds(RISK, rag) == ["outcome"]


def test_the_restated_text_must_be_of_the_cited_passage() -> None:
    """Passage 1 is about supplier concentration; restating passage 0 while citing 1 fails."""
    text = f"SIMULATED: SIM Widgets depends on a single casing supplier [{passage_citation(1)}]."
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == ["outcome"]


SUPPLIER = "depending on a single supplier for widget casings"


def test_an_unchanged_claim_does_not_meet_an_added_risk_factor() -> None:
    """The restated paragraph is the added one; claiming it stayed the same is wrong."""
    for text in (
        f"SIMULATED: SIM Widgets' risk factor on {SUPPLIER} was unchanged [{SIM_ACCESSION}].",
        f"SIMULATED: SIM Widgets has not changed its risk on {SUPPLIER} [{SIM_ACCESSION}].",
        f"SIMULATED: Its risk on {SUPPLIER} remained the same [{SIM_ACCESSION}].",
    ):
        assert kinds(RISK, transcript(text, (DIFF_CALL,))) == ["outcome"], text


def test_the_claimed_kind_must_be_the_kind_of_the_restated_change() -> None:
    text = f"SIMULATED: SIM Widgets removed its risk factor on {SUPPLIER} [{SIM_ACCESSION}]."
    assert kinds(RISK, transcript(text, (DIFF_CALL,))) == ["outcome"]


def test_rag_must_restate_a_paragraph_the_oracle_reports_as_added() -> None:
    """RAG restates its cited passage, but the oracle's diff added another paragraph."""
    tariffs = risk_diff_evidence(
        "SIMULATED: Tariffs on imported steel could raise our production costs sharply.",
        call_id="oracle-0",
    )
    text = (
        f"SIMULATED: SIM Widgets added a risk factor on {SUPPLIER} [{passage_citation(0)}], "
        f"which its earlier 10-K did not name [{SIM_PREVIOUS_ACCESSION}/risk_factors/1]."
    )
    rag = transcript(text, (BOTH_FILINGS,), offered=RAG_TOOLS, oracle=(tariffs,))
    assert kinds(RISK, rag) == ["outcome"]
    unchanged = text.replace("added a risk factor on", "kept its risk factor, unchanged, on")
    rag = transcript(unchanged, (BOTH_FILINGS,), offered=RAG_TOOLS, oracle=ORACLE)
    assert kinds(RISK, rag) == ["outcome"]


def no_change(evidence: Evidence) -> Evidence:
    result: dict[str, Any] = json.loads(evidence.result)
    result.update(added=0, unchanged=3, changes=[], changes_total=0)
    return evidence.model_copy(update={"result": json.dumps(result)})


def test_when_the_diff_reports_no_change_only_a_no_change_answer_passes() -> None:
    same = (
        "SIMULATED: SIM Widgets' risk factors were unchanged from its earlier 10-K "
        f"[{SIM_ACCESSION}]."
    )
    assert kinds(RISK, transcript(same, (no_change(DIFF_CALL),))) == []
    added = f"SIMULATED: SIM Widgets added a risk factor on {SUPPLIER} [{SIM_ACCESSION}]."
    assert kinds(RISK, transcript(added, (no_change(DIFF_CALL),))) == ["outcome"]
