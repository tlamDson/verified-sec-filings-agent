"""The Sources panel of a figure answer lists the filing, not every passage a search returned.

A search returns 5-8 passages whether or not they bear on the figure (UX-2: "Net income"
listed a passage on Services gross margin). When the turn shows a figure card, a passage
is listed only if the answer cites it; a text question keeps every passage. Figures come
from the recorded Apple facts; passages are simulated (`faithfulness_kit`).
"""

from faithfulness_kit import passage_citation, run_tool, search_evidence

from sec_agent.agent.answer import Evidence
from sec_agent.api.cited_sources import cited_sources
from sec_agent.api.present import present
from sec_agent.tools.context import FactsContext

_PASSAGES = ("SIMULATED Services gross margin increased.", "SIMULATED effective tax rate.")


def _revenue(facts: FactsContext) -> Evidence:
    return run_tool(facts, "get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)


def _kinds(text: str, evidence: list[Evidence]) -> list[tuple[str, str]]:
    view = cited_sources(present(evidence), text)
    return [(c.kind, c.key) for c in view.citations]


def test_a_figure_answer_lists_its_filing_and_no_uncited_passage(
    facts_ctx: FactsContext,
) -> None:
    evidence = [_revenue(facts_ctx), search_evidence(*_PASSAGES)]
    shown = _kinds("SIMULATED: revenue was $391,035 million.", evidence)
    assert [kind for kind, _ in shown] == ["filing"]


def test_a_figure_answer_keeps_the_passage_it_cites(facts_ctx: FactsContext) -> None:
    evidence = [_revenue(facts_ctx), search_evidence(*_PASSAGES)]
    text = f"SIMULATED: revenue was $391,035 million; the tax rate fell [{passage_citation(1)}]."
    shown = _kinds(text, evidence)
    assert [kind for kind, _ in shown] == ["filing", "passage"]
    assert shown[1][1] == passage_citation(1)


def test_a_text_answer_keeps_every_passage() -> None:
    shown = _kinds("SIMULATED: margins rose.", [search_evidence(*_PASSAGES)])
    assert shown == [("passage", passage_citation(0)), ("passage", passage_citation(1))]


def test_cards_are_left_as_they_are(facts_ctx: FactsContext) -> None:
    view = present([_revenue(facts_ctx), search_evidence(*_PASSAGES)])
    assert cited_sources(view, "SIMULATED").cards == view.cards
