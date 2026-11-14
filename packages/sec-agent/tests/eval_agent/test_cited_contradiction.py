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
