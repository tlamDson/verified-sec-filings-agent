"""Duration classes from a period's start and end dates.

Filers use calendar months or 52/53-week years, so lengths vary by a few days: a 13-week
quarter is 90 days end minus start, a 14-week one 97; a 53-week year 370. Each class takes
a window around its nominal length; anything else (one month, four months, two years) is
not a period this product answers about.
"""

import datetime as dt
from typing import Literal

DurationClass = Literal["quarter", "six_months", "nine_months", "annual"]
PeriodKind = Literal["instant", "quarter", "ytd", "annual"]
"""How a stored fact's period reads: six and nine months are year-to-date (`ytd`)."""

_WINDOWS: tuple[tuple[int, int, DurationClass], ...] = (
    (80, 100, "quarter"),
    (170, 195, "six_months"),
    (260, 290, "nine_months"),
    (350, 380, "annual"),
)


def classify_duration(start: dt.date, end: dt.date) -> DurationClass | None:
    days = (end - start).days
    for low, high, name in _WINDOWS:
        if low <= days <= high:
            return name
    return None


def period_kind(duration: DurationClass | None) -> PeriodKind:
    """The stored kind: None (no start date) is an instant."""
    match duration:
        case None:
            return "instant"
        case "six_months" | "nine_months":
            return "ytd"
        case "quarter" | "annual":
            return duration
