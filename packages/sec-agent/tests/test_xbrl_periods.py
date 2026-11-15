"""Duration classes from start and end dates (52/53-week years included)."""

import datetime as dt

import pytest

from sec_agent.xbrl.periods import classify_duration


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2023-01-01", "2023-12-31", "annual"),  # calendar year
        ("2023-01-30", "2024-01-28", "annual"),  # NVIDIA FY2024, 52 weeks
        ("2022-09-25", "2023-09-30", "annual"),  # Apple FY2023, 53 weeks
        ("2023-10-30", "2024-01-28", "quarter"),  # 13 weeks
        ("2022-09-25", "2022-12-31", "quarter"),  # Apple Q1 FY2023, 14 weeks
        ("2023-04-01", "2023-06-30", "quarter"),
        ("2023-01-01", "2023-06-30", "six_months"),
        ("2022-09-25", "2023-04-01", "six_months"),  # 27 weeks
        ("2023-01-01", "2023-09-30", "nine_months"),
        ("2023-01-30", "2023-10-29", "nine_months"),
        ("2023-01-01", "2023-01-31", None),  # one month
        ("2023-01-01", "2023-04-30", None),  # four months
        ("2022-01-01", "2023-12-31", None),  # two years
        ("2023-12-31", "2023-01-01", None),  # end before start
    ],
)
def test_classify_duration(start: str, end: str, expected: str | None) -> None:
    got = classify_duration(dt.date.fromisoformat(start), dt.date.fromisoformat(end))
    assert got == expected
