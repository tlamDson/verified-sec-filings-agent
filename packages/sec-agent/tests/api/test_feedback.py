"""POST /v1/feedback: a thumbs up or down on one answered turn.

The model is simulated and the users are made up for the tests. Feedback of the simulated
cohort is kept apart from real feedback and only proves the feedback path works.
"""

from typing import Any

import pytest
from api_kit import OTHER, REAL, SIM, THREAD, TODAY, Api, api_of, auth
from llm_fakes import ScriptedProvider, says

from sec_agent.api.identity import Identity
from sec_agent.tools.context import FactsContext


def _api(facts: FactsContext, turns: int = 1) -> Api:
    return api_of(facts, ScriptedProvider("a", [says("SIMULATED answer.")] * turns))


def _rate(api: Api, rating: Any, *, user: Identity = REAL, turn: Any = 1, thread: str = THREAD):
    body = {"thread_id": thread, "turn": turn, "rating": rating}
    return api.client.post("/v1/feedback", json=body, headers=auth(user))


def test_a_user_rates_a_turn_they_asked(facts_ctx: FactsContext) -> None:
    api = _api(facts_ctx)
    api.chat("A question?")
    response = _rate(api, "up")
    assert (response.status_code, response.content) == (204, b"")
    counts = api.store.cohort_counts(TODAY, TODAY)["real"]
    assert (counts.thumbs_up, counts.thumbs_down) == (1, 0)


def test_changing_the_rating_replaces_it(facts_ctx: FactsContext) -> None:
    api = _api(facts_ctx)
    api.chat("A question?")
    _rate(api, "up")
    assert _rate(api, "down").status_code == 204
    counts = api.store.cohort_counts(TODAY, TODAY)["real"]
    assert (counts.thumbs_up, counts.thumbs_down) == (0, 1)


def test_a_turn_that_was_never_asked_cannot_be_rated(facts_ctx: FactsContext) -> None:
    api = _api(facts_ctx)
    api.chat("A question?")
    for response in (
        _rate(api, "up", turn=2),
        _rate(api, "up", thread="thread-0002"),
        _rate(api, "up", user=OTHER),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "unknown_turn"
    assert api.store.cohort_counts(TODAY, TODAY)["real"].thumbs_up == 0


def test_simulated_feedback_is_counted_in_the_simulated_cohort_only(
    facts_ctx: FactsContext,
) -> None:
    api = _api(facts_ctx, turns=2)
    api.chat("A question?", user=SIM)
    api.chat("A question?", user=REAL)
    _rate(api, "down", user=SIM)
    counts = api.store.cohort_counts(TODAY, TODAY)
    assert (counts["simulated"].thumbs_up, counts["simulated"].thumbs_down) == (0, 1)
    assert (counts["real"].thumbs_up, counts["real"].thumbs_down) == (0, 0)


@pytest.mark.parametrize(
    ("rating", "turn"), [("great", 1), ("", 1), (None, 1), ("up", 0), ("up", -1), ("up", "one")]
)
def test_a_malformed_rating_is_refused(facts_ctx: FactsContext, rating: Any, turn: Any) -> None:
    api = _api(facts_ctx)
    api.chat("A question?")
    response = _rate(api, rating, turn=turn)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "invalid_request")


def test_feedback_needs_a_token(facts_ctx: FactsContext) -> None:
    api = _api(facts_ctx)
    body = {"thread_id": THREAD, "turn": 1, "rating": "up"}
    assert api.client.post("/v1/feedback", json=body).status_code == 401
