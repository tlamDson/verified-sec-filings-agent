"""Who is asking: a short-lived token the web app signs and the API verifies.

The browser never talks to the API. The web app's server checks the user's session, then
calls the API with a compact HS256 token (header.claims.signature, base64url) made with a
secret both sides hold. The claims name the user (`sub`), the cohort (`real` or
`simulated`), this API (`aud`) and a lifetime of at most `MAX_LIFETIME_SECONDS`.

A simulated account is always `sim:...` and nothing else is: the cohort label cannot
drift from the account it belongs to.
"""

import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Cohort = Literal["real", "simulated"]
COHORTS: tuple[Cohort, ...] = ("real", "simulated")
AUDIENCE = "sec-agent-api"
SIMULATED_PREFIX = "sim:"
MAX_USER_ID_CHARS = 120
MAX_LIFETIME_SECONDS = 300
DEFAULT_TTL_SECONDS = 60
_HEADER = {"alg": "HS256", "typ": "JWT"}


class IdentityError(Exception):
    """The token is missing, malformed, expired or not signed by the web app."""


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(min_length=1, max_length=MAX_USER_ID_CHARS)
    """`<provider>:<account id>`, or `sim:<email>` for a simulated account."""
    cohort: Cohort

    @model_validator(mode="after")
    def _cohort_matches_account(self) -> Self:
        if not self.user_id.isprintable() or self.user_id != self.user_id.strip():
            raise ValueError("the user id holds a control character or outer space")
        if self.user_id.startswith(SIMULATED_PREFIX) != (self.cohort == "simulated"):
            raise ValueError("the cohort does not match the account")
        return self


def sign_token(
    identity: Identity,
    secret: str,
    *,
    now: dt.datetime,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """The token the web app sends; here for tests and for Python callers of the API."""
    issued = int(now.timestamp())
    claims = {
        "sub": identity.user_id,
        "cohort": identity.cohort,
        "aud": AUDIENCE,
        "iat": issued,
        "exp": issued + ttl_seconds,
    }
    signing_input = f"{_encode(_HEADER)}.{_encode(claims)}"
    return f"{signing_input}.{_b64(_signature(signing_input, secret))}"


def verify_token(token: str, secret: str, *, now: dt.datetime) -> Identity:
    """The identity a valid token names. The error never repeats any part of the token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise IdentityError("the token is not three base64url parts")
    header, claims, signature = parts
    if _decode(header) != _HEADER:
        raise IdentityError("the token is not an HS256 token")
    if not hmac.compare_digest(_unb64(signature), _signature(f"{header}.{claims}", secret)):
        raise IdentityError("the token's signature does not match")
    return _identity(_decode(claims), int(now.timestamp()))


def _identity(claims: dict[str, Any], now: int) -> Identity:
    if claims.get("aud") != AUDIENCE:
        raise IdentityError("the token is for another service")
    expires, issued = _whole(claims.get("exp")), _whole(claims.get("iat", now))
    if expires is None or issued is None:
        raise IdentityError("the token has no usable lifetime")
    if expires <= now:
        raise IdentityError("the token has expired")
    if expires - min(issued, now) > MAX_LIFETIME_SECONDS:
        raise IdentityError(f"the token lives longer than {MAX_LIFETIME_SECONDS} seconds")
    user = {"user_id": claims.get("sub"), "cohort": claims.get("cohort")}
    try:
        return Identity.model_validate(user)
    except ValidationError as error:
        raise IdentityError(f"the token's user is not valid: {_problems(error)}") from None


def _problems(error: ValidationError) -> str:
    """Which field is wrong, or the fixed text of the account rule; never the value."""
    problems = {
        str(e["loc"][0]) if e["loc"] else e["msg"].removeprefix("Value error, ")
        for e in error.errors(include_input=False, include_url=False)
    }
    return "; ".join(sorted(problems))


def _whole(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _signature(signing_input: str, secret: str) -> bytes:
    return hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()


def _encode(value: dict[str, Any]) -> str:
    return _b64(json.dumps(value, separators=(",", ":")).encode())


def _decode(part: str) -> dict[str, Any]:
    try:
        value: object = json.loads(_unb64(part))
    except ValueError:
        raise IdentityError("the token is not readable") from None
    if not isinstance(value, dict):
        raise IdentityError("the token is not readable")
    return cast(dict[str, Any], value)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(part: str) -> bytes:
    try:
        return base64.b64decode(part + "=" * (-len(part) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise IdentityError("the token is not readable") from None
