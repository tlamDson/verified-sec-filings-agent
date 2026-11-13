"""The simulated users' web client, against a stand-in for the Next.js app that forwards to
the real API in process. The model is simulated and the accounts are simulated test
accounts; nothing here touches the network.
"""

import datetime as dt

import pytest
from api_kit import TODAY, api_of
from llm_fakes import ScriptedProvider, call, calls, says
from sim_web_fake import PASSWORD, FakeWebApp

from sec_agent.llm.errors import ProviderUnavailableError
from sec_agent.simusers.roster import SimAccount
from sec_agent.simusers.web_client import SimSignInError, WebSession
from sec_agent.tools.context import FactsContext

ACCOUNT = SimAccount(number=7, persona="student")
THREAD = "sim-20261113-07-1"
ASKED_ON = dt.date(2026, 11, 13)


def _signed_in(web: FakeWebApp) -> WebSession:
    return WebSession.sign_in(web.client(), ACCOUNT, PASSWORD)


def test_it_signs_in_with_the_simulated_credentials_provider() -> None:
    web = FakeWebApp()
    _signed_in(web)
    assert web.sign_ins == ["sim-07@example.com"]
    assert web.paths[:3] == [
        "GET /api/auth/csrf",
        "POST /api/auth/callback/simulated",
        "GET /api/auth/session",
    ]


def test_a_wrong_password_is_a_sign_in_error() -> None:
    with pytest.raises(SimSignInError):
        WebSession.sign_in(FakeWebApp().client(), ACCOUNT, "wrong")


def test_a_session_that_is_not_simulated_is_refused() -> None:
    """The driver never sends traffic under anything but the simulated cohort."""
    with pytest.raises(SimSignInError):
        _signed_in(FakeWebApp(session_cohort="real"))


def test_a_turn_through_the_web_app_and_the_api_is_read_from_its_events(
    facts_ctx: FactsContext,
) -> None:
    provider = ScriptedProvider(
        "a",
        [
            calls(call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)),
            says("SIMULATED: Apple reported revenue of $391,035 million for fiscal 2024."),
        ],
    )
    api = api_of(facts_ctx, provider)
    outcome = _signed_in(FakeWebApp(api)).ask(
        THREAD, "What was Apple's revenue in fiscal 2024?", ASKED_ON
    )
    assert (outcome.kind, outcome.turn, outcome.verdict) == ("answered", 1, "pass")
    assert outcome.evidence >= 1
    assert outcome.seconds >= 0
    assert api.store.cohort_counts(TODAY, TODAY)["simulated"].turns == 1
    assert api.store.cohort_counts(TODAY, TODAY)["real"].turns == 0


def test_a_degraded_turn_is_read_as_degraded(facts_ctx: FactsContext) -> None:
    api = api_of(facts_ctx, ScriptedProvider("down", [ProviderUnavailableError("SIMULATED 503")]))
    outcome = _signed_in(FakeWebApp(api)).ask(
        THREAD, "What was Apple's revenue in fiscal 2024?", ASKED_ON
    )
    assert outcome.kind == "degraded"


def test_the_daily_limit_is_read_as_limited() -> None:
    web = FakeWebApp()
    web.chat_status = 429
    outcome = _signed_in(web).ask(THREAD, "A question?", ASKED_ON)
    assert (outcome.kind, outcome.turn) == ("limited", None)


def test_another_refusal_is_read_as_an_error() -> None:
    web = FakeWebApp()
    web.chat_status = 502
    assert _signed_in(web).ask(THREAD, "A question?", ASKED_ON).kind == "error"


def test_a_rating_reaches_the_api_as_simulated_feedback(facts_ctx: FactsContext) -> None:
    api = api_of(facts_ctx, ScriptedProvider("a", [says("SIMULATED answer.")]))
    session = _signed_in(FakeWebApp(api))
    session.ask(THREAD, "A question?", ASKED_ON)
    assert session.rate(THREAD, 1, "down") is True
    assert session.rate(THREAD, 9, "up") is False
    counts = api.store.cohort_counts(TODAY, TODAY)
    assert (counts["simulated"].thumbs_down, counts["real"].thumbs_down) == (1, 0)
