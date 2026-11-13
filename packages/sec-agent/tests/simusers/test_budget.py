"""The driver's daily budget: a share of the LLM quota, at most half of it."""

import pytest
from pydantic import ValidationError

from sec_agent.simusers.budget import MAX_SHARE, QuotaBudget


def test_by_default_the_driver_takes_half_the_quota_at_four_calls_a_question() -> None:
    budget = QuotaBudget(llm_calls_per_day=1000)
    assert (budget.calls_per_question, budget.share, MAX_SHARE) == (4, 0.5, 0.5)
    assert budget.questions_per_day == 125


def test_the_budget_rounds_down_and_never_floats_past_the_share() -> None:
    assert (
        QuotaBudget(llm_calls_per_day=100, share=0.29, calls_per_question=1).questions_per_day == 29
    )
    assert QuotaBudget(llm_calls_per_day=10, calls_per_question=4).questions_per_day == 1
    assert QuotaBudget(llm_calls_per_day=7, calls_per_question=4).questions_per_day == 0


@pytest.mark.parametrize("share", [0.0, 0.51, 1.0])
def test_a_share_above_half_or_zero_is_refused(share: float) -> None:
    with pytest.raises(ValidationError):
        QuotaBudget(llm_calls_per_day=1000, share=share)
