"""create_app: the routes of the API over what it depends on.

    GET  /healthz       liveness, no token
    GET  /v1/me         the caller's cohort and today's usage
    POST /v1/chat       one turn, as server-sent events (`events`)
    POST /v1/feedback   thumbs up or down on a turn the caller asked

Every route but `/healthz` needs the identity token of `identity`. A question is counted
against the user's UTC day before the turn starts; past the limit it is refused with 429
and no model is called. Routes are plain functions, so FastAPI runs them, and the turn's
stream, on worker threads: the agent, its tools and the stores are synchronous.
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from sec_agent.agent.config import AgentConfig
from sec_agent.api.config import ApiConfig
from sec_agent.api.errors import ApiError, install_error_handlers, unauthorized
from sec_agent.api.events import Usage
from sec_agent.api.identity import Cohort, Identity, IdentityError, verify_token
from sec_agent.api.store import ApiStore, Feedback
from sec_agent.api.turns import TurnAgent, TurnRequest, TurnStreamer
from sec_agent.degraded.lookup import Tools
from sec_agent.tools.companies import CompanyDirectory

THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
MAX_QUESTION_CHARS = AgentConfig().max_question_chars
MAX_DATE_SKEW_DAYS = 1
"""How far the user's date may be from the server's UTC date: one time zone day."""
_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_BODY = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@dataclass(frozen=True)
class ApiDeps:
    agent: TurnAgent
    tools: Tools
    """Runs the deterministic lookups of degraded mode; the agent's own tool runner."""
    companies: CompanyDirectory
    store: ApiStore
    config: ApiConfig
    now: Callable[[], dt.datetime] = _utc_now


class ChatBody(BaseModel):
    model_config = _BODY

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    """The conversation, chosen by the browser; private to the user who sends it."""
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    asked_on: dt.date | None = None
    """The user's own date, for relative periods (E6)."""


class FeedbackBody(BaseModel):
    model_config = _BODY

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    turn: int = Field(ge=1)
    rating: Literal["up", "down"]


class Me(BaseModel):
    cohort: Cohort
    usage: Usage


def create_app(deps: ApiDeps) -> FastAPI:
    app = FastAPI(title="sec-agent API", docs_url=None, redoc_url=None, openapi_url=None)
    install_error_handlers(app)
    streamer = TurnStreamer(
        agent=deps.agent, tools=deps.tools, companies=deps.companies, store=deps.store
    )
    limit = deps.config.daily_questions

    def caller(authorization: Annotated[str | None, Header()] = None) -> Identity:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme != "Bearer":
            raise unauthorized()
        try:
            return verify_token(token.strip(), deps.config.auth_secret, now=deps.now())
        except IdentityError:
            raise unauthorized() from None

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/me")
    def me(user: Annotated[Identity, Depends(caller)]) -> Me:
        now = deps.now()
        used = deps.store.questions_used(user.user_id, _utc_day(now))
        return Me(cohort=user.cohort, usage=Usage(used=used, limit=limit, resets_at=_reset(now)))

    @app.post("/v1/chat")
    def chat(body: ChatBody, user: Annotated[Identity, Depends(caller)]) -> StreamingResponse:
        now = deps.now()
        used = deps.store.charge_question(user, _utc_day(now), limit)
        if used is None:
            raise _daily_limit(limit, now)
        request = TurnRequest(
            identity=user,
            thread_id=body.thread_id,
            question=body.question,
            asked_on=_asked_on(body.asked_on, _utc_day(now)),
            asked_at=now,
            usage=Usage(used=used, limit=limit, resets_at=_reset(now)),
        )
        return StreamingResponse(
            streamer.stream(request), media_type="text/event-stream", headers=_STREAM_HEADERS
        )

    @app.post("/v1/feedback", status_code=204)
    def feedback(body: FeedbackBody, user: Annotated[Identity, Depends(caller)]) -> Response:
        kept = deps.store.save_feedback(
            Feedback(
                user_id=user.user_id,
                cohort=user.cohort,
                thread_id=body.thread_id,
                turn=body.turn,
                rating=body.rating,
                at=deps.now(),
            )
        )
        if not kept:
            raise ApiError(404, "unknown_turn", "There is no such turn of yours to rate.")
        return Response(status_code=204)

    return app


def _utc_day(now: dt.datetime) -> dt.date:
    return now.astimezone(dt.UTC).date()


def _reset(now: dt.datetime) -> dt.datetime:
    """The start of the next UTC day, when the daily count starts again."""
    tomorrow = _utc_day(now) + dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow, dt.time(), tzinfo=dt.UTC)


def _asked_on(claimed: dt.date | None, today: dt.date) -> dt.date:
    if claimed is not None and abs((claimed - today).days) <= MAX_DATE_SKEW_DAYS:
        return claimed
    return today


def _daily_limit(limit: int, now: dt.datetime) -> ApiError:
    reset = _reset(now)
    return ApiError(
        429,
        "daily_limit",
        f"You have asked {limit} of {limit} questions today. The count resets at 00:00 UTC.",
        extra={"limit": limit, "resets_at": reset.isoformat().replace("+00:00", "Z")},
        headers={"Retry-After": str(int((reset - now).total_seconds()))},
    )
