"""The thumbs a simulated user gives, by criteria written down before any answer is seen.

Simulated ratings only exercise the feedback path; they never measure quality.
"""

import pytest

from sec_agent.simusers.feedback import rating_for
from sec_agent.simusers.outcome import TurnOutcome


def _outcome(**fields: object) -> TurnOutcome:
    base: dict[str, object] = {
        "kind": "answered",
        "turn": 1,
        "verdict": "pass",
        "removed": 0,
        "evidence": 2,
        "seconds": 1.0,
    }
    return TurnOutcome.model_validate(base | fields)


def test_a_checked_answer_with_evidence_gets_a_thumbs_up() -> None:
    assert rating_for(_outcome()) == "up"


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "step_limit"},
        {"kind": "blocked", "verdict": "blocked"},
        {"verdict": "trimmed", "removed": 1},
        {"removed": 2},
    ],
)
def test_an_unfinished_or_trimmed_answer_gets_a_thumbs_down(fields: dict[str, object]) -> None:
    assert rating_for(_outcome(**fields)) == "down"


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "degraded", "verdict": None},
        {"kind": "error", "turn": None, "verdict": None},
        {"kind": "limited", "turn": None, "verdict": None},
        {"evidence": 0},
    ],
)
def test_degraded_failed_or_evidence_free_turns_get_no_rating(fields: dict[str, object]) -> None:
    assert rating_for(_outcome(**fields)) is None
