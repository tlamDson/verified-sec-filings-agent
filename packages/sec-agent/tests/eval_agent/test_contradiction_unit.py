"""`contradiction.contradicts`: opposite negation between a clause and the source clause it
restates. Sources and sentences are simulated."""

from sec_agent.eval.agent.contradiction import contradicts, negated

SOURCE = "We depend on a single supplier for our widget casings. Demand grew in 2025."


def test_negated_finds_negation_cues_outside_citations() -> None:
    assert negated("It does not depend on a supplier")
    assert negated("It isn't a supplier")
    assert negated("It has no supplier")
    assert not negated("It depends on a supplier [0001-24-000001/risk_factors/no]")


def test_a_negated_restatement_contradicts() -> None:
    assert contradicts("It does not depend on a single supplier for widget casings.", SOURCE)


def test_a_plain_restatement_does_not() -> None:
    assert not contradicts("It depends on a single supplier for widget casings.", SOURCE)


def test_a_negated_source_restated_plainly_contradicts() -> None:
    negated_source = "We do not depend on a single supplier for our widget casings."
    assert contradicts("It depends on a single supplier for widget casings.", negated_source)
    assert not contradicts(
        "It does not depend on a single supplier for widget casings.", negated_source
    )


def test_a_negation_in_another_clause_of_the_sentence_does_not_count() -> None:
    sentence = (
        "It depends on a single supplier for widget casings, which the 2024 10-K did not name."
    )
    assert not contradicts(sentence, SOURCE)


def test_a_sentence_sharing_too_few_words_is_not_judged() -> None:
    assert not contradicts("It does not depend on a supplier.", SOURCE)
