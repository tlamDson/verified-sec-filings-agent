"""Who may ask, how often, and what a request must look like.

The API runs in process; the model is simulated. Users and secrets are made up for tests.
"""

import datetime as dt

import pytest
from api_kit import NOW, OTHER, REAL, SIM, THREAD, TODAY, api_of, auth, event
from llm_fakes import ScriptedProvider, says

from sec_agent.api.identity import sign_token
from sec_agent.tools.context import FactsContext

ANSWER = "SIMULATED answer."
OTHER_SECRET = "another-secret-0123456789abcdef0123456789"


def _model(replies: int = 1) -> ScriptedProvider:
    return ScriptedProvider("a", [says(ANSWER)] * replies)


def test_health_needs_no_token(facts_ctx: FactsContext) -> None:
    response = api_of(facts_ctx).client.get("/healthz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Basic abc"},
        {"Authorization": f"Bearer {sign_token(REAL, OTHER_SECRET, now=NOW)}"},
        auth(REAL, now=NOW - dt.timedelta(hours=1)),
    ],
)
@pytest.mark.parametrize(("method", "path"), [("POST", "/v1/chat"), ("GET", "/v1/me")])
def test_a_request_without_a_valid_token_is_refused_before_anything_runs(
    facts_ctx: FactsContext, headers: dict[str, str], method: str, path: str
) -> None:
    model = _model()
    api = api_of(facts_ctx, model)
    body = {"thread_id": THREAD, "question": "A question?"}
    response = api.client.request(method, path, json=body, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"
    assert model.requests == []
    assert api.store.questions_used(REAL.user_id, TODAY) == 0


def test_me_reports_the_cohort_and_todays_usage(facts_ctx: FactsContext) -> None:
    api = api_of(facts_ctx, _model(), daily_questions=7)
    before = api.client.get("/v1/me", headers=auth(SIM)).json()
    assert before == {
        "cohort": "simulated",
        "usage": {"used": 0, "limit": 7, "resets_at": "2026-11-14T00:00:00Z"},
    }
    api.chat("A question?", user=SIM)
    assert api.client.get("/v1/me", headers=auth(SIM)).json()["usage"]["used"] == 1
    assert api.client.get("/v1/me", headers=auth(REAL)).json()["usage"]["used"] == 0


def test_past_the_daily_limit_a_question_is_refused_and_no_model_is_called(
    facts_ctx: FactsContext,
) -> None:
    model = _model(2)
    api = api_of(facts_ctx, model, daily_questions=2)
    assert event(api.chat("First?"), "turn")["usage"]["used"] == 1
    assert event(api.chat("Second?"), "turn")["usage"]["used"] == 2

    refused = api.chat("Third?")
    assert refused.status_code == 429
    assert refused.json()["error"] == {
        "code": "daily_limit",
        "message": "You have asked 2 of 2 questions today. The count resets at 00:00 UTC.",
        "limit": 2,
        "resets_at": "2026-11-14T00:00:00Z",
    }
    assert refused.headers["retry-after"] == str(14 * 3600 + 29 * 60 + 45)
    assert len(model.requests) == 2


def test_one_users_limit_does_not_stop_another(facts_ctx: FactsContext) -> None:
    api = api_of(facts_ctx, _model(2), daily_questions=1)
    assert api.chat("Mine?", user=REAL).status_code == 200
    assert api.chat("Mine again?", user=REAL).status_code == 429
    assert api.chat("Theirs?", user=OTHER).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"thread_id": THREAD, "question": ""},
        {"thread_id": THREAD, "question": "   "},
        {"thread_id": THREAD, "question": "x" * 2001},
        {"thread_id": THREAD},
        {"question": "No thread?"},
        {"thread_id": "short", "question": "A question?"},
        {"thread_id": "has space in it", "question": "A question?"},
        {"thread_id": "colon:in-thread", "question": "A question?"},
        {"thread_id": "t" * 65, "question": "A question?"},
        {"thread_id": THREAD, "question": "A question?", "asked_on": "yesterday"},
        {"thread_id": THREAD, "question": "A question?", "extra": 1},
        [],
    ],
)
def test_a_malformed_question_is_refused_and_not_counted(
    facts_ctx: FactsContext, body: object
) -> None:
    model = _model()
    api = api_of(facts_ctx, model)
    response = api.client.post("/v1/chat", json=body, headers=auth(REAL))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert "x" * 50 not in error["message"], "the message does not echo what was sent"
    assert model.requests == []
    assert api.store.questions_used(REAL.user_id, TODAY) == 0


def test_a_question_is_trimmed_before_it_reaches_the_model(facts_ctx: FactsContext) -> None:
    model = _model()
    api_of(facts_ctx, model).chat("   Padded question?  \n")
    assert model.requests[0].messages[-1]["content"] == "Padded question?"


def test_an_unknown_path_and_a_wrong_method_use_the_same_error_shape(
    facts_ctx: FactsContext,
) -> None:
    client = api_of(facts_ctx).client
    missing = client.get("/v1/nothing", headers=auth(REAL))
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    wrong = client.get("/v1/chat", headers=auth(REAL))
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (405, "method_not_allowed")
