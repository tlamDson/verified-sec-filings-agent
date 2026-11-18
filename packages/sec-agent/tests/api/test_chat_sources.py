"""POST /v1/chat on a figure question whose turn also searched filing text (UX-2).

The agent is simulated: it replays a recorded Apple revenue lookup and two simulated
passages, then answers without citing either passage.
"""

import datetime as dt
from collections.abc import Iterator

from api_kit import api_of, event
from faithfulness_kit import run_tool, search_evidence

from sec_agent.agent.answer import Answer, Evidence
from sec_agent.tools.context import FactsContext


class _FigureAgent:
    def __init__(self, evidence: tuple[Evidence, ...], text: str) -> None:
        self._evidence, self._text = evidence, text

    def steps(
        self, thread_id: str, question: str, *, asked_on: dt.date
    ) -> Iterator[Evidence | Answer]:
        yield from self._evidence
        yield Answer(
            thread_id=thread_id,
            turn=1,
            asked_on=asked_on,
            status="answered",
            reason=None,
            text=self._text,
            evidence=self._evidence,
            llm_calls=(),
        )


def test_the_answer_event_lists_only_the_filing_for_a_figure(facts_ctx: FactsContext) -> None:
    evidence = (
        run_tool(facts_ctx, "get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024),
        search_evidence("SIMULATED Services gross margin.", "SIMULATED tax rate."),
    )
    agent = _FigureAgent(evidence, "SIMULATED: revenue was $391,035 million.")
    answer = event(api_of(facts_ctx, agent=agent).chat("Apple revenue 2024?"), "answer")
    assert [c["kind"] for c in answer["citations"]] == ["filing"]
