"""One simulated account signed in to the web app, asking and rating like a browser would.

It goes through the deployed path (Next.js route handlers, then the API, agent, tools and
LLM router), never straight to the API. Sign-in uses the app's Auth.js credentials
provider `simulated` (csrf token, credentials callback, then the session), and the session
must name this account in the `simulated` cohort before any question is sent.
"""

import datetime as dt
import time
from collections.abc import Callable
from typing import cast

import httpx

from sec_agent.simusers.events import outcome_of, sse_events
from sec_agent.simusers.feedback import Rating
from sec_agent.simusers.outcome import TurnOutcome
from sec_agent.simusers.roster import SimAccount

SIMULATED_PROVIDER = "simulated"
"""The Auth.js provider id of `web/lib/auth/identity.ts`."""
TURN_TIMEOUT_SECONDS = 180.0


class SimSignInError(Exception):
    """The account could not sign in, or the session is not this simulated account."""


class WebSession:
    def __init__(self, http: httpx.Client, account: SimAccount, clock: Callable[[], float]) -> None:
        self._http = http
        self._account = account
        self._clock = clock

    @classmethod
    def sign_in(
        cls,
        http: httpx.Client,
        account: SimAccount,
        password: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> "WebSession":
        try:
            csrf = http.get("/api/auth/csrf").raise_for_status().json()["csrfToken"]
            http.post(
                f"/api/auth/callback/{SIMULATED_PROVIDER}",
                data={
                    "csrfToken": csrf,
                    "email": account.email,
                    "password": password,
                    "json": "true",
                },
            ).raise_for_status()
            session: object = http.get("/api/auth/session").raise_for_status().json()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise SimSignInError(
                f"{account.email}: sign-in failed ({type(error).__name__})"
            ) from None
        identity = (
            cast(dict[str, object], session).get("identity") if isinstance(session, dict) else None
        )
        expected = {"id": account.user_id, "cohort": "simulated"}
        if identity != expected:
            raise SimSignInError(f"{account.email}: the session is not this simulated account")
        return cls(http, account, clock)

    def ask(self, thread_id: str, question: str, asked_on: dt.date) -> TurnOutcome:
        body = {"thread_id": thread_id, "question": question, "asked_on": asked_on.isoformat()}
        started = self._clock()
        try:
            with self._http.stream(
                "POST", "/api/chat", json=body, timeout=TURN_TIMEOUT_SECONDS
            ) as response:
                if response.status_code == 429:
                    return TurnOutcome(kind="limited", seconds=self._since(started))
                if response.status_code != 200:
                    return TurnOutcome(kind="error", seconds=self._since(started))
                events = sse_events(response.iter_lines())
        except httpx.HTTPError:
            return TurnOutcome(kind="error", seconds=self._since(started))
        return outcome_of(events, self._since(started))

    def rate(self, thread_id: str, turn: int, rating: Rating) -> bool:
        body = {"thread_id": thread_id, "turn": turn, "rating": rating}
        try:
            return self._http.post("/api/feedback", json=body).status_code == 204
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        self._http.close()

    def _since(self, started: float) -> float:
        return max(0.0, self._clock() - started)
