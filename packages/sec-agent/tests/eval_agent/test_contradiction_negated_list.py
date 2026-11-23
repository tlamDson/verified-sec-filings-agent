"""T-0005: a list under a negation ("none of the following: ...") keeps that negation.

The stored cases keep a real committed agent transcript (`results/agent/test/agent.jsonl`)
and replace only the answer with one sentence that cites a real passage and negates the
list it restates. The same sentence without the negation still passes, so the failure
comes from the negation alone. The replaced answers are written by the test; the passages
are real filing text. The unit cases use simulated text.
"""

from functools import cache
from pathlib import Path

import pytest

from sec_agent.eval.agent.checks import check_scenario
from sec_agent.eval.agent.contradiction import contradicts
from sec_agent.eval.agent.scenarios import Scenario, Transcript, read_scenarios
from sec_agent.golden.jsonl import read_jsonl

ROOT = Path(__file__).resolve().parents[4]
CITE = "[0001163165-25-000012/risk_factors/0]"

# (scenario, contradicting answer, agreeing answer); the key is a passage the stored
# transcript retrieved for the scenario's search check.
CASES = (
    (
        "a1-033",
        "Its results depend on none of the following: the sales prices for crude oil, "
        f"bitumen, LNG, natural gas, or NGLs {CITE}.",
        "Its results depend on the sales prices for crude oil, bitumen, LNG, natural gas, "
        f"and NGLs {CITE}.",
    ),
    (
        "a1-033",
        "ConocoPhillips is exposed to none of the following: the effects of volatile "
        f"commodity prices, or prolonged periods of low commodity prices {CITE}.",
        "ConocoPhillips is exposed to the effects of volatile commodity prices, or prolonged "
        f"periods of low commodity prices {CITE}.",
    ),
)

PLAIN = "We depend on a single supplier for our widget casings."


@cache
def _scenarios() -> dict[str, Scenario]:
    path = ROOT / "data" / "golden" / "agent_scenarios.jsonl"
    return {s.id: s for s in read_scenarios(path) if s.split == "test"}


@cache
def _stored() -> dict[str, Transcript]:
    path = ROOT / "results" / "agent" / "test" / "agent.jsonl"
    return {t.scenario_id: t for t in read_jsonl(path, Transcript)}


def _kinds(scenario_id: str, text: str) -> list[str]:
    transcript = _stored()[scenario_id].model_copy(update={"text": text})
    return [f.kind for f in check_scenario(_scenarios()[scenario_id], transcript).failures]


@pytest.mark.parametrize(("scenario_id", "contradicting", "agreeing"), CASES)
def test_a_negated_list_contradicting_its_stored_passage_fails_a1(
    scenario_id: str, contradicting: str, agreeing: str
) -> None:
    assert _kinds(scenario_id, agreeing) == []
    assert _kinds(scenario_id, contradicting) == ["outcome"]


@pytest.mark.parametrize(
    "sentence",
    [
        "It depends on none of the following: a contract manufacturer, a sole vendor, "
        "or a single supplier for widget casings.",
        "It does not depend on any of the following: a contract manufacturer; a sole vendor; "
        "or a single supplier for widget casings.",
    ],
)
def test_a_list_under_a_negation_keeps_that_negation(sentence: str) -> None:
    assert contradicts(sentence, PLAIN)


def test_a_negated_list_in_the_passage_restated_plainly_contradicts() -> None:
    source = (
        "We depend on none of the following: a contract manufacturer, a sole vendor, "
        "or a single supplier for our widget casings."
    )
    assert contradicts("It depends on a single supplier for widget casings.", source)


def test_a_negated_list_restated_with_its_negation_agrees() -> None:
    source = (
        "We depend on none of the following: a contract manufacturer, a sole vendor, "
        "or a single supplier for our widget casings."
    )
    sentence = (
        "It depends on none of the following: a contract manufacturer, a sole vendor, "
        "or a single supplier for widget casings."
    )
    assert not contradicts(sentence, source)
