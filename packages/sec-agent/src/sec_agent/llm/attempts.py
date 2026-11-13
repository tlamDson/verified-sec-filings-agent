"""What the router did with one provider for one request."""

from typing import Literal, NamedTuple

Outcome = Literal[
    "ok",
    "breaker_open",
    "quota_exhausted",
    "rate_limited",
    "unavailable",
    "bad_response",
    "rejected",
]


class Attempt(NamedTuple):
    provider: str
    outcome: Outcome
    detail: str
    """The error's message when a call failed; empty otherwise."""
