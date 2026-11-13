"""POST /v1/chat: one turn, streamed as server-sent events.

The API runs in process. The model is simulated (every reply is scripted by the test); the
tools are real and read the recorded Apple and NVIDIA facts, so the figures below are what
SEC reported. Users are made up for the tests.
"""

import datetime as dt
from collections.abc import Iterator

import pytest
from api_kit import OTHER, REAL, SIM, THREAD, TODAY, api_of, event, events
from llm_fakes import ScriptedProvider, call, calls, says

from sec_agent.agent.answer import Answer, Evidence
from sec_agent.agent.errors import ConversationConflictError
from sec_agent.agent.notices import DEGRADED_TEXT
from sec_agent.faithfulness.notices import BLOCKED_TEXT
from sec_agent.llm.errors import ProviderUnavailableError
from sec_agent.tools.context import FactsContext

REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
QUESTION = "What was Apple's revenue in fiscal 2024?"
ANSWER = "SIMULATED: Apple reported revenue of $391,035 million for fiscal 2024."
UNTRACED = "SIMULATED: Apple reported revenue of $555,000 million for fiscal 2024."
DOWN = ProviderUnavailableError("503 from provider")


def test_a_turn_is_streamed_as_turn_then_evidence_then_answer(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), says(ANSWER)])
    response = api_of(facts_ctx, model).chat(QUESTION)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert [name for name, _ in events(response)] == ["turn", "evidence", "answer"]

    turn = event(response, "turn")
    assert turn == {
        "thread_id": THREAD,
        "cohort": "real",
        "usage": {"used": 1, "limit": 20, "resets_at": "2026-11-14T00:00:00Z"},
    }

    (card,) = event(response, "evidence")["cards"]
    assert (card["kind"], card["value"], card["period_end"]) == (
        "fact",
        "391035000000",
        "2024-09-28",
    )

    answer = event(response, "answer")
    assert (answer["thread_id"], answer["turn"]) == (THREAD, 1)
    assert (answer["status"], answer["reason"], answer["degraded"]) == ("answered", None, False)
    assert answer["text"] == ANSWER
    assert answer["cards"] == [card]
    assert [c["kind"] for c in answer["citations"]] == ["filing"]
    assert answer["charts"] == []
    assert answer["check"] == {"verdict": "pass", "figures": 1, "traced": 1, "removed": 0}


def test_several_years_of_one_figure_come_with_a_chart(facts_ctx: FactsContext) -> None:
    lookups = [
        call("get_fact", f"c{year}", company="AAPL", concept="revenue", fiscal_year=year)
        for year in (2023, 2024)
    ]
    model = ScriptedProvider("a", [calls(*lookups), says("SIMULATED answer without figures.")])
    answer = event(api_of(facts_ctx, model).chat("Apple revenue 2023 and 2024"), "answer")
    (chart,) = answer["charts"]
    assert (chart["kind"], chart["title"], chart["unit"]) == ("trend", "Revenue", "USD")
    assert [(p["x"], p["value"]) for p in chart["series"][0]["points"]] == [
        ("FY2023", "383285000000"),
        ("FY2024", "391035000000"),
    ]


def test_an_answer_with_a_figure_that_cannot_be_traced_is_withheld(
    facts_ctx: FactsContext,
) -> None:
    """The checker's verdict reaches the user: the notice, and the tool figures."""
    model = ScriptedProvider("a", [calls(REVENUE), says(UNTRACED)])
    answer = event(api_of(facts_ctx, model).chat(QUESTION), "answer")
    assert (answer["status"], answer["reason"]) == ("blocked", "untraced_figures")
    assert answer["text"] == BLOCKED_TEXT
    assert "555,000" not in str(answer)
    assert answer["cards"][0]["value"] == "391035000000"
    assert answer["check"]["verdict"] == "blocked"
    assert (answer["check"]["figures"], answer["check"]["traced"]) == (1, 0)


def test_when_no_model_answers_the_figures_are_looked_up_without_one(
    facts_ctx: FactsContext,
) -> None:
    """Degraded mode: deterministic cards, no model prose, and the answer says so."""
    model = ScriptedProvider("a", [DOWN])
    response = api_of(facts_ctx, model).chat(QUESTION)
    assert [name for name, _ in events(response)] == ["turn", "evidence", "answer"]
    answer = event(response, "answer")
    assert (answer["status"], answer["reason"], answer["degraded"]) == (
        "degraded",
        "llm_unavailable",
        True,
    )
    assert answer["text"] == DEGRADED_TEXT
    assert answer["check"] is None
    (card,) = answer["cards"]
    assert (card["kind"], card["company"]["ticker"], card["fiscal_year"]) == ("fact", "AAPL", 2024)
    assert (card["value"], card["period_end"]) == ("391035000000", "2024-09-28")
    assert event(response, "evidence")["cards"] == [card]
    assert len(model.requests) == 1, "no further model call was made for the cards"


def test_a_degraded_turn_keeps_the_figures_the_agent_already_fetched(
    facts_ctx: FactsContext,
) -> None:
    net_income = call("get_fact", "c1", company="AAPL", concept="net_income", fiscal_year=2024)
    model = ScriptedProvider("a", [calls(net_income), DOWN])
    answer = event(api_of(facts_ctx, model).chat(QUESTION), "answer")
    assert (answer["status"], answer["degraded"]) == ("degraded", True)
    assert [(c["call_id"], c["concept"]) for c in answer["cards"]] == [("c1", "net_income")]


def test_a_degraded_turn_with_nothing_to_look_up_has_no_cards(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [DOWN])
    response = api_of(facts_ctx, model).chat("Should I buy tech stocks?")
    assert [name for name, _ in events(response)] == ["turn", "answer"]
    answer = event(response, "answer")
    assert (answer["degraded"], answer["cards"], answer["charts"]) == (True, [], [])
    assert "not investment advice" in answer["text"].lower()


def test_a_follow_up_continues_the_conversation(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [says("SIMULATED first."), says("SIMULATED second.")])
    api = api_of(facts_ctx, model)
    assert event(api.chat("First question?"), "answer")["turn"] == 1
    assert event(api.chat("Second question?"), "answer")["turn"] == 2
    history = [m["content"] for m in model.requests[1].messages if m["role"] != "system"]
    assert history == ["First question?", "SIMULATED first.", "Second question?"]


def test_two_users_with_the_same_thread_id_never_share_a_conversation(
    facts_ctx: FactsContext,
) -> None:
    model = ScriptedProvider("a", [says("SIMULATED for one."), says("SIMULATED for another.")])
    api = api_of(facts_ctx, model)
    api.chat("A private question?", user=REAL)
    answer = event(api.chat("Another question?", user=OTHER), "answer")
    assert answer["turn"] == 1
    assert all("private" not in str(m["content"]) for m in model.requests[1].messages)


def test_the_cohort_of_a_simulated_user_is_carried_through(facts_ctx: FactsContext) -> None:
    api = api_of(facts_ctx, ScriptedProvider("a", [says("SIMULATED answer.")]))
    assert event(api.chat("A question?", user=SIM), "turn")["cohort"] == "simulated"
    counts = api.store.cohort_counts(TODAY, TODAY)
    assert (counts["simulated"].turns, counts["simulated"].users) == (1, 1)
    assert (counts["real"].turns, counts["real"].users) == (0, 0)


def test_every_turn_is_logged_with_whether_it_was_degraded(facts_ctx: FactsContext) -> None:
    api = api_of(facts_ctx, ScriptedProvider("a", [says("SIMULATED answer."), DOWN]))
    api.chat("A question?")
    api.chat("Another question?")
    counts = api.store.cohort_counts(TODAY, TODAY)["real"]
    assert (counts.turns, counts.degraded_turns, counts.conversations) == (2, 1, 1)


@pytest.mark.parametrize(
    ("asked_on", "anchored_on"),
    [
        ("2026-11-12", "2026-11-12"),  # the user's evening, a time zone behind
        ("2026-11-14", "2026-11-14"),
        ("2020-01-01", "2026-11-13"),  # not the user's date: the server's is used
        (None, "2026-11-13"),
    ],
)
def test_relative_periods_anchor_on_the_users_date_when_it_is_plausible(
    facts_ctx: FactsContext, asked_on: str | None, anchored_on: str
) -> None:
    """E6: the date a question is anchored on is the user's, within a day of the server's."""
    model = ScriptedProvider("a", [says("SIMULATED answer.")])
    api_of(facts_ctx, model).chat("Revenue last quarter?", asked_on=asked_on)
    assert f"Today is {anchored_on}." in str(model.requests[0].messages[0]["content"])


class _ConflictingAgent:
    """Stands in for an agent whose conversation another replica advanced first."""

    def steps(
        self, thread_id: str, question: str, *, asked_on: dt.date
    ) -> Iterator[Evidence | Answer]:
        raise ConversationConflictError(thread_id)
        yield


class _BrokenAgent:
    def steps(
        self, thread_id: str, question: str, *, asked_on: dt.date
    ) -> Iterator[Evidence | Answer]:
        raise RuntimeError("SIMULATED failure with a secret detail")
        yield


def test_a_conversation_another_request_advanced_ends_with_an_error_event(
    facts_ctx: FactsContext,
) -> None:
    response = api_of(facts_ctx, agent=_ConflictingAgent()).chat(QUESTION)
    assert response.status_code == 200
    assert [name for name, _ in events(response)] == ["turn", "error"]
    assert event(response, "error")["code"] == "conversation_conflict"
    assert REAL.user_id not in str(event(response, "error")), "the internal thread id stays in"


def test_an_unexpected_failure_ends_the_stream_with_an_error_that_tells_nothing(
    facts_ctx: FactsContext,
) -> None:
    response = api_of(facts_ctx, agent=_BrokenAgent()).chat(QUESTION)
    assert [name for name, _ in events(response)] == ["turn", "error"]
    error = event(response, "error")
    assert error["code"] == "internal_error"
    assert "secret detail" not in str(error)
