"""A1 text outcome: a contradiction is judged even when the passage spreads what the sentence
restates over several of its sentences, and "not only" / "not limited to" are not negations.
Passages and answers are simulated."""

from faithfulness_kit import passage_citation, search_evidence
from text_outcome_kit import TEXT, kinds, transcript

from sec_agent.eval.agent.contradiction import contradicts, negated

SPREAD = "We depend on one vendor for parts. That single supplier makes all of our widget casings."
NEGATED_SPREAD = (
    "SIMULATED: SIM Widgets does not depend on a single supplier for its widget casings "
    f"[{passage_citation(0)}]."
)


def test_a_negation_of_a_passage_spread_over_two_sentences_fails_a1() -> None:
    source = search_evidence(f"SIMULATED: {SPREAD}")
    assert kinds(TEXT, transcript(NEGATED_SPREAD, (source,))) == ["outcome"]


def test_a_negation_of_a_passage_spread_over_two_sentences_contradicts() -> None:
    assert contradicts("It does not depend on a single supplier for widget casings.", SPREAD)
    assert not contradicts("It depends on a single supplier for widget casings.", SPREAD)


def test_a_plain_sentence_against_a_spread_negated_passage_contradicts() -> None:
    source = "We buy parts from many vendors. No single supplier makes our widget casings."
    assert contradicts("A single supplier makes its widget casings.", source)


def test_not_only_and_not_limited_to_are_not_negations() -> None:
    assert not negated("It depends not only on a single supplier but also on one carrier")
    assert not negated("Risks include, but are not limited to, a single supplier")
    assert not negated("It relies not just on one supplier")
    assert negated("It does not depend on a single supplier")


def test_a_faithful_not_only_answer_passes_a1() -> None:
    source = search_evidence("SIMULATED: We depend on a single supplier for our widget casings.")
    text = (
        "SIMULATED: SIM Widgets depends not only on a single supplier for its widget casings "
        f"but also on one carrier [{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (source,))) == []


def test_a_not_only_passage_restated_plainly_passes_a1() -> None:
    source = search_evidence(
        "SIMULATED: We depend not only on a single supplier for our widget casings, "
        "but also on one carrier."
    )
    text = (
        "SIMULATED: SIM Widgets depends on a single supplier for its widget casings "
        f"[{passage_citation(0)}]."
    )
    assert kinds(TEXT, transcript(text, (source,))) == []
