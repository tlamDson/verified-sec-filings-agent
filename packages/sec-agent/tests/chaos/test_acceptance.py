"""The plan's chaos acceptance check on a k6 run, decided by code, not by reading k6 output:
with a replica killed under 200 simulated users the turn error rate stays under the limit
and conversations resume (all follow-ups, and those of interrupted conversations)."""

import json
from pathlib import Path

import pytest

from sec_agent.chaos.acceptance import ERROR_RATE_LIMIT, breaches
from sec_agent.chaos.k6_summary import LoadSummary, parse_k6_summary

FIXTURE = Path(__file__).parent.parent / "fixtures" / "k6" / "summary.sim.json"


def _summary(**changes: int) -> LoadSummary:
    summary = parse_k6_summary(json.loads(FIXTURE.read_text("utf-8")))
    return summary.model_copy(update=changes)


def test_the_limit_is_five_percent() -> None:
    assert ERROR_RATE_LIMIT == 0.05


def test_a_run_under_every_limit_passes() -> None:
    assert breaches(_summary()) == []


@pytest.mark.parametrize(
    ("changes", "metric"),
    [
        ({"turns": 400, "turns_failed": 20}, "turn_failed"),
        ({"resumes": 200, "resumes_failed": 10}, "resume_failed"),
        ({"interrupted": 20, "interrupted_failed": 1}, "interrupted_resume_failed"),
    ],
)
def test_a_rate_at_the_limit_is_a_breach_naming_the_metric(
    changes: dict[str, int], metric: str
) -> None:
    """k6's threshold is `rate<0.05`, so exactly 5% already fails."""
    found = breaches(_summary(**changes))
    assert len(found) == 1
    assert metric in found[0]
    assert "0.05" in found[0]


@pytest.mark.parametrize(
    "changes",
    [
        {"turns": 400, "turns_failed": 19},
        {"resumes": 200, "resumes_failed": 9},
        {"interrupted": 21, "interrupted_failed": 1},
    ],
)
def test_a_rate_just_under_the_limit_passes(changes: dict[str, int]) -> None:
    assert breaches(_summary(**changes)) == []


def test_every_breach_is_reported() -> None:
    found = breaches(
        _summary(turns_failed=40, resumes_failed=20, interrupted=10, interrupted_failed=5)
    )
    assert len(found) == 3


def test_a_run_with_no_interrupted_conversation_checks_no_recovery_of_one() -> None:
    assert breaches(_summary(interrupted=0, interrupted_failed=0)) == []


def test_a_run_with_no_follow_up_fails_the_resume_check() -> None:
    """Conversations must resume; a run that never tried a follow-up cannot show that."""
    found = breaches(_summary(resumes=0, resumes_failed=0, interrupted=0, interrupted_failed=0))
    assert len(found) == 1
    assert "resume_failed" in found[0]
