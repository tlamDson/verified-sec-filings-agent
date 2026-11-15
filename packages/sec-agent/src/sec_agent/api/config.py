"""The API's settings, read from the environment once at start."""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

SECRET_ENV_VAR = "API_AUTH_SECRET"
DAILY_QUESTIONS_ENV_VAR = "API_DAILY_QUESTIONS"
MIN_SECRET_CHARS = 32
PLACEHOLDER_PREFIX = "change-me"
"""How `.env.example` starts every secret; a copied placeholder is public, so it is refused."""
DEFAULT_DAILY_QUESTIONS = 20
"""Questions one user may ask per UTC day. A setting, not a measurement: the free
provider's daily quota divided by the calls a question makes decides what it can be."""


class ApiConfigError(Exception):
    """The API cannot start on its environment. The message never repeats a value."""


class ApiConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    auth_secret: str = Field(min_length=MIN_SECRET_CHARS, repr=False)
    """Shared with the web app, which signs each request's identity token with it."""
    daily_questions: PositiveInt = DEFAULT_DAILY_QUESTIONS


def config_from_env(environ: Mapping[str, str]) -> ApiConfig:
    secret = environ.get(SECRET_ENV_VAR, "").strip()
    if len(secret) < MIN_SECRET_CHARS or secret.startswith(PLACEHOLDER_PREFIX):
        raise ApiConfigError(
            f"set {SECRET_ENV_VAR} to a random secret of at least {MIN_SECRET_CHARS} "
            "characters, the same one the web app holds"
        )
    return ApiConfig(auth_secret=secret, daily_questions=_daily_questions(environ))


def _daily_questions(environ: Mapping[str, str]) -> int:
    text = environ.get(DAILY_QUESTIONS_ENV_VAR, "").strip()
    if not text:
        return DEFAULT_DAILY_QUESTIONS
    if not text.isdecimal() or int(text) < 1:
        raise ApiConfigError(f"{DAILY_QUESTIONS_ENV_VAR} must be a positive whole number")
    return int(text)
