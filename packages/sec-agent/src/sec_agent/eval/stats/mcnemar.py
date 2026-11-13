"""Exact McNemar test for two systems graded on the same questions.

Only discordant pairs carry information: `a_only` questions system A got right and B wrong,
`b_only` the reverse. Under the null both are equally likely, so the two-sided p value is
the binomial tail 2 * P(X <= min(a_only, b_only)) for X ~ Bin(a_only + b_only, 1/2),
capped at 1. Exact, not the chi-square approximation: discordant counts are often small.
"""

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field


class McNemarResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int = Field(ge=0)
    """Paired questions."""
    a_only: int = Field(ge=0)
    b_only: int = Field(ge=0)
    p_value: float = Field(ge=0, le=1)


def mcnemar(a: Sequence[bool], b: Sequence[bool]) -> McNemarResult:
    """`a[i]` and `b[i]` are the two systems' outcomes on question i."""
    if len(a) != len(b):
        raise ValueError(f"need paired outcomes, got {len(a)} and {len(b)}")
    a_only = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    b_only = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    return McNemarResult(n=len(a), a_only=a_only, b_only=b_only, p_value=_exact_p(a_only, b_only))


def _exact_p(a_only: int, b_only: int) -> float:
    discordant = a_only + b_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, i) for i in range(min(a_only, b_only) + 1))
    return min(1.0, 2 * tail / 2**discordant)
