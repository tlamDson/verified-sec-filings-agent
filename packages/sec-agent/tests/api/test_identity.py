"""The identity token: who is asking, signed by the web app, verified by the API.

Every user and secret here is made up for a test.
"""

import base64
import datetime as dt
import hashlib
import hmac
import json
from typing import Any

import pytest
from api_kit import NOW, REAL, SECRET, SIM

from sec_agent.api.identity import (
    AUDIENCE,
    MAX_LIFETIME_SECONDS,
    Identity,
    IdentityError,
    sign_token,
    verify_token,
)

WEB_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJnaXRodWI6NDIiLCJjb2hvcnQiOiJyZWFsIiwiYXVkIjoic2VjLWFnZW50LWFwaSIsImlhdCI6"
    "MTc5NDU2MjIxNSwiZXhwIjoxNzk0NTYyMjc1fQ."
    "SIm7T2_D7Cmhg9X4ClDtUvntGY7J1fUpjv9vzA_a5FQ"
)
"""What `signApiToken` of the web app returns for REAL at NOW with SECRET
(`web/tests/token.test.ts` asserts the same text)."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _forge(claims: object, *, alg: str = "HS256", secret: str = SECRET) -> str:
    header = _b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    payload = _b64(json.dumps(claims).encode())
    signature = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256)
    return f"{header}.{payload}.{_b64(signature.digest())}"


def _claims(**changes: Any) -> dict[str, Any]:
    iat = int(NOW.timestamp())
    return {
        "sub": REAL.user_id,
        "cohort": "real",
        "aud": AUDIENCE,
        "iat": iat,
        "exp": iat + 60,
        **changes,
    }


@pytest.mark.parametrize("user", [REAL, SIM])
def test_a_signed_token_names_its_user_and_cohort(user: Identity) -> None:
    token = sign_token(user, SECRET, now=NOW)
    assert verify_token(token, SECRET, now=NOW + dt.timedelta(seconds=30)) == user


def test_the_token_the_web_app_signs_is_accepted() -> None:
    assert verify_token(WEB_TOKEN, SECRET, now=NOW) == REAL
    assert sign_token(REAL, SECRET, now=NOW) == WEB_TOKEN


def test_an_expired_token_is_refused() -> None:
    token = sign_token(REAL, SECRET, now=NOW, ttl_seconds=60)
    with pytest.raises(IdentityError, match="expired"):
        verify_token(token, SECRET, now=NOW + dt.timedelta(seconds=61))


def test_a_token_signed_with_another_secret_is_refused() -> None:
    token = sign_token(REAL, "another-secret-0123456789abcdef0123456789", now=NOW)
    with pytest.raises(IdentityError):
        verify_token(token, SECRET, now=NOW)


def test_a_token_whose_claims_were_edited_is_refused() -> None:
    header, _, signature = sign_token(REAL, SECRET, now=NOW).split(".")
    edited = _b64(json.dumps(_claims(sub="github:1")).encode())
    with pytest.raises(IdentityError):
        verify_token(f"{header}.{edited}.{signature}", SECRET, now=NOW)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-token",
        "a.b",
        "a.b.c.d",
        "!!!.???.***",
        _forge(_claims(), alg="none"),
        _forge(_claims(), alg="HS512"),
        _forge(_claims(aud="another-service")),
        _forge(_claims(cohort="vip")),
        _forge(_claims(sub="")),
        _forge(_claims(sub="x" * 121)),
        _forge(_claims(sub="line\nbreak")),
        _forge(_claims(exp="soon")),
        _forge({k: v for k, v in _claims().items() if k != "exp"}),
        _forge(_claims(exp=int(NOW.timestamp()) + MAX_LIFETIME_SECONDS + 1)),
        _forge(["not", "an", "object"]),
    ],
)
def test_a_malformed_or_unexpected_token_is_refused(token: str) -> None:
    with pytest.raises(IdentityError):
        verify_token(token, SECRET, now=NOW)


def test_the_error_never_repeats_the_token() -> None:
    token = _forge(_claims(aud="another-service"))
    with pytest.raises(IdentityError) as caught:
        verify_token(token, SECRET, now=NOW)
    assert token not in str(caught.value)
    assert token.split(".")[2] not in str(caught.value)


@pytest.mark.parametrize(
    ("user_id", "cohort"),
    [("sim:sim-07@example.com", "real"), ("github:42", "simulated")],
)
def test_a_simulated_account_can_never_carry_the_real_cohort_or_the_reverse(
    user_id: str, cohort: str
) -> None:
    """Simulated accounts are `sim:...`; the cohort label cannot drift from the account."""
    with pytest.raises(IdentityError, match="cohort"):
        verify_token(_forge(_claims(sub=user_id, cohort=cohort)), SECRET, now=NOW)
    with pytest.raises(ValueError, match="cohort"):
        Identity.model_validate({"user_id": user_id, "cohort": cohort})
