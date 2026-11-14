"""A1 text outcome: a negation covers every item of the list it governs, so a negated
enumeration that contradicts its cited passage fails. Passages and answers are simulated."""

from faithfulness_kit import passage_citation, search_evidence
from text_outcome_kit import TEXT, kinds, transcript

from sec_agent.eval.agent.contradiction import contradicts

PLAIN = "We depend on a single supplier for our widget casings."
LISTED = (
    "We do not depend on a contract manufacturer, a sole vendor, or a single supplier "
    "for our widget casings."
)


def test_a_negated_enumeration_contradicting_the_passage_fails_a1() -> None:
    text = (
        "SIMULATED: SIM Widgets does not depend on a contract manufacturer, a sole vendor, "
        f"or a single supplier for its widget casings [{passage_citation(0)}]."
    )
    source = search_evidence(f"SIMULATED: {PLAIN}")
    assert kinds(TEXT, transcript(text, (source,))) == ["outcome"]


def test_a_negated_enumeration_in_the_passage_restated_plainly_contradicts() -> None:
    assert contradicts("It depends on a single supplier for widget casings.", LISTED)


def test_a_negated_enumeration_restated_with_its_negation_passes_a1() -> None:
    text = (
        "SIMULATED: SIM Widgets does not depend on a contract manufacturer, a sole vendor, "
        f"or a single supplier for its widget casings [{passage_citation(0)}]."
    )
    source = search_evidence(f"SIMULATED: {LISTED}")
    assert kinds(TEXT, transcript(text, (source,))) == []


def test_a_negation_ends_at_a_new_clause() -> None:
    sentence = "It has no backup contract, and it depends on a single supplier for widget casings."
    assert not contradicts(sentence, PLAIN)
