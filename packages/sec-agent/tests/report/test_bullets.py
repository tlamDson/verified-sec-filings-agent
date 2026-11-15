"""Resume bullets: numbers are formatted runs.csv values, never typed by hand."""

import pytest
from report_kit import bullet_rows, run

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


def test_dev_and_simulated_rows_are_never_quoted_as_test_results() -> None:
    rows = [
        *bullet_rows(),
        run("N1", "b2", 0.99, split="dev"),
        run("N1", "b2", 0.98, cohort="simulated"),
        run("R1_ndcg@10", "hybrid", 0.97, split="train"),
    ]
    text = render_bullets(rows)
    assert "75.0%" in text
    for wrong in ("99.0%", "98.0%", "97.0%"):
        assert wrong not in text


def test_only_a_dev_row_is_a_missing_test_row() -> None:
    rows = [r for r in bullet_rows() if not (r.metric == "N1" and r.system == "b2")]
    rows.append(run("N1", "b2", 0.99, split="dev"))
    with pytest.raises(MissingRunError):
        render_bullets(rows)
