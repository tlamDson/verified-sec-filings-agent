"""Resume bullets: numbers are formatted runs.csv values, never typed by hand."""

import pytest
from report_kit import bullet_rows
from sec_agent.report.bullets import MissingRunError, render_bullets


def test_bullets_quote_measured_values() -> None:
    text = render_bullets(bullet_rows())
    for shown in ("75.0%", "15.0%", "78.0%", "16.0%", "n=300", "n=50"):
        assert shown in text


def test_bullets_follow_what_how_design_impact() -> None:
    text = render_bullets(bullet_rows())
    for label in ("What:", "How:", "Design:", "Impact:"):
        assert label in text


def test_bullets_say_where_the_numbers_come_from() -> None:
    assert "runs.csv" in render_bullets(bullet_rows())


def test_missing_row_is_an_error_not_a_guess() -> None:
    with pytest.raises(MissingRunError):
        render_bullets(bullet_rows()[:3])
