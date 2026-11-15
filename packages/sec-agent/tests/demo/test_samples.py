"""Sample answers for the demo: the question, the shown text, its citations and passages."""

from demo_kit import ACC, KEY, fact, scenario, search, transcript

from sec_agent.demo.samples import pick_samples


def test_a_sample_carries_the_last_turn_and_each_cited_passage() -> None:
    text = f'Chevron warns "costs could rise" [{KEY}].'
    tr = transcript("a1-001", text, [search([{"citation": KEY, "text": "costs could rise"}])])
    [sample] = pick_samples([scenario("a1-001", question="Climate risk?")], [tr])
    assert sample.question == "Climate risk?"
    assert sample.answer == text
    assert [(p.citation, p.text) for p in sample.passages] == [(KEY, "costs could rise")]


def test_passages_follow_citation_order_once_each() -> None:
    other = f"{ACC}/risk_factors/14"
    text = f"A [{other}]. B [{KEY}]. C [{other}]."
    ev = search([{"citation": KEY, "text": "b"}, {"citation": other, "text": "a"}])
    [sample] = pick_samples([scenario("a1-001")], [transcript("a1-001", text, [ev])])
    assert [p.citation for p in sample.passages] == [other, KEY]


def test_numeric_answer_shows_tool_call_and_filing_link() -> None:
    url = "https://www.sec.gov/Archives/edgar/data/1/2-index.htm"
    tr = transcript("a1-001", "Revenue was $56,141,000,000.", [fact(url)])
    [sample] = pick_samples([scenario("a1-001", "value")], [tr])
    assert sample.passages == ()
    [tool] = sample.tools
    assert tool.name == "get_fact"
    assert '"concept": "revenue"' in tool.arguments
    assert tool.filing_urls == (url,)


def test_skips_unanswered_unsourced_and_unresolved_citations() -> None:
    ev = search([{"citation": KEY, "text": "t"}])
    scenarios = [scenario(f"a1-00{i}") for i in range(1, 5)]
    transcripts = [
        transcript("a1-001", f"x [{KEY}]", [ev], status="blocked"),
        transcript("a1-002", "no source at all", []),
        transcript("a1-003", f"x [{ACC}/risk_factors/99]", [ev]),
        transcript("a1-004", f"x [{KEY}]", [ev]),
    ]
    assert [s.scenario_id for s in pick_samples(scenarios, transcripts)] == ["a1-004"]


def test_round_robin_over_categories_up_to_limit() -> None:
    cats = ["value", "value", "value", "ratio", "text"]
    scenarios = [scenario(f"a1-00{i}", c) for i, c in enumerate(cats, 1)]
    transcripts = [transcript(s.id, "x", [fact()]) for s in scenarios]
    picked = pick_samples(scenarios, transcripts, limit=4)
    assert [s.scenario_id for s in picked] == ["a1-001", "a1-004", "a1-005", "a1-002"]


def test_only_agent_transcripts_are_sampled() -> None:
    tr = transcript("a1-001", "x", [fact()], system="rag")
    assert pick_samples([scenario("a1-001")], [tr]) == []
