"""A1 text outcome: a cited sentence that contradicts the passage it cites is not an answer.

Sharing words with a passage is not enough to restate it: "does not depend on a single
supplier" shares every content word with "we depend on a single supplier" and says the
opposite. The sentence is judged by code against the cited passage (its negation), never by
a model. A differing figure is already `unfaithful`. Passages and answers are simulated.
"""

from faithfulness_kit import SIM_ACCESSION, passage_citation, search_evidence
from text_outcome_kit import (
    DIFF_CALL,
    PASSAGES,
    RAG_TOOLS,
    RISK,
    TEXT,
    kinds,
    transcript,
)

from sec_agent.agent.answer import Evidence


def test_a_cited_negation_of_the_passage_fails_for_the_agent_and_rag() -> None:
    text = (
        "SIMULATED: SIM Widgets does not depend on a single supplier for its widget casings "
        f"[{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == ["outcome"]
    assert kinds(TEXT, transcript(text, (PASSAGES,), offered=RAG_TOOLS)) == ["outcome"]


def test_a_negated_passage_restated_without_the_negation_fails() -> None:
    negated = search_evidence(
        "SIMULATED: We do not depend on a single supplier for our widget casings."
    )
    text = (
        "SIMULATED: SIM Widgets depends on a single supplier for its widget casings "
        f"[{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (negated,))) == ["outcome"]


def test_a_negated_passage_restated_with_its_negation_passes() -> None:
    negated = search_evidence(
        "SIMULATED: We do not depend on a single supplier for our widget casings."
    )
    text = (
        "SIMULATED: SIM Widgets does not depend on a single supplier for its widget casings "
        f"[{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (negated,))) == []


def test_a_sentence_contradicting_one_cited_passage_fails_even_if_it_restates_another() -> None:
    text = (
        "SIMULATED: SIM Widgets does not depend on a single supplier for its widget casings "
        f"[{passage_citation(0)}][{passage_citation(1)}]."
    )
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == ["outcome"]


def test_a_contradicting_sentence_does_not_hide_a_faithful_one() -> None:
    text = (
        "SIMULATED: SIM Widgets does not depend on a single supplier for its widget casings "
        f"[{passage_citation(0)}]. SIM Widgets depends on a single casing supplier "
        f"[{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (PASSAGES,))) == []


def test_the_agent_risk_diff_is_unchanged_by_the_passage_check() -> None:
    text = (
        "SIMULATED: SIM Widgets added a risk factor: it depends on a single supplier for "
        f"widget casings [{SIM_ACCESSION}]."
    )
    assert kinds(RISK, transcript(text, (DIFF_CALL,))) == []


def one_passage(text: str) -> Evidence:
    return search_evidence(f"SIMULATED: {text}")


def test_a_negation_in_another_clause_of_the_passage_is_not_a_contradiction() -> None:
    source = one_passage(
        "We depend on a single supplier for our widget casings, "
        "and we do not expect that to change."
    )
    text = (
        "SIMULATED: SIM Widgets depends on a single supplier for its widget casings "
        f"[{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (source,))) == []


def test_a_contradiction_split_by_commas_is_still_judged() -> None:
    source = one_passage("We depend on a single supplier for our widget casings and housings.")
    text = (
        "SIMULATED: SIM Widgets does not depend on a single supplier for its casings, nor on "
        f"its widget housings [{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (source,))) == ["outcome"]


def test_the_opposite_direction_of_a_change_contradicts() -> None:
    source = one_passage("Casing costs increased sharply across our widget supplier contracts.")
    same = (
        "SIMULATED: SIM Widgets says casing costs increased sharply across its widget supplier "
        f"contracts [{passage_citation(0)}]."
    )
    opposite = same.replace("increased", "decreased")
    assert kinds(TEXT, transcript(same, (source,))) == []
    assert kinds(TEXT, transcript(opposite, (source,))) == ["outcome"]


def test_a_failure_to_do_what_the_sentence_says_is_done_contradicts() -> None:
    source = one_passage(
        "We fail to meet customer demand for widget casings from our single supplier."
    )
    text = (
        "SIMULATED: SIM Widgets meets customer demand for widget casings from its single "
        f"supplier [{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (source,))) == ["outcome"]
