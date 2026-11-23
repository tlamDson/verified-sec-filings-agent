"""T-0006 on real model answers: the advice filter keeps what follows a decline, and a
formatted recommendation ("**Recommendation:** Buy") is caught by the filter and the S1
grader.

The answers are the 19 G-red advice answers the local model (Qwen) wrote in the unguarded
S1 run (`results/safety/v1/none.jsonl`) that decline advice ("I cannot provide investment
advice ..."), then offer or give reported figures; 4 of them state a figure.
"""

import json
from pathlib import Path

import pytest

from sec_agent.eval.safety.advice_grade import gives_advice
from sec_agent.guardrails.answer import guard_answer

RECORDED = Path(__file__).resolve().parents[4] / "results" / "safety" / "v1" / "none.jsonl"
FORMATTED = "**Recommendation:** Buy"


def _advice_answers() -> list[tuple[str, str]]:
    rows = [json.loads(line) for line in RECORDED.read_text(encoding="utf-8").splitlines()]
    return [
        (r["item_id"], r["text"])
        for r in rows
        if r["item_id"].startswith("gred-advice") and "cannot provide" in r["text"].lower()
    ]


ANSWERS = _advice_answers()


def test_the_recorded_sample_declines_then_gives_figures() -> None:
    assert len(ANSWERS) == 19
    assert sum("$" in text or "%" in text for _, text in ANSWERS) == 4


@pytest.mark.parametrize(("item_id", "text"), ANSWERS)
def test_a_decline_and_the_figures_after_it_are_kept(item_id: str, text: str) -> None:
    guard = guard_answer(text, canary=None, advice_requested=True)
    assert guard.advice_dropped == 0, item_id
    assert guard.text.startswith(text.rstrip()), item_id
    assert not gives_advice(guard.text), item_id


@pytest.mark.parametrize(("item_id", "text"), ANSWERS)
def test_a_formatted_recommendation_is_dropped_and_the_rest_kept(item_id: str, text: str) -> None:
    answer = f"{text.rstrip()}\n\n{FORMATTED}"
    assert gives_advice(answer), item_id
    guard = guard_answer(answer, canary=None, advice_requested=True)
    assert guard.advice_dropped == 1, item_id
    assert FORMATTED not in guard.text, item_id
    assert guard.text.startswith(text.rstrip()), item_id
    assert not gives_advice(guard.text), item_id


def test_a_formatted_recommendation_alone_is_caught() -> None:
    assert gives_advice(FORMATTED)
    guard = guard_answer(FORMATTED, canary=None, advice_requested=True)
    assert guard.advice_dropped == 1
    assert FORMATTED not in guard.text
